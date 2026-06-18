"""
tournament.py
Simulacion Monte Carlo del torneo completo: fase de grupos y eliminacion directa.

Los partidos ya disputados quedan fijos; solo se simulan los que faltan, de modo
que las probabilidades se vuelven mas nitidas conforme avanza el Mundial. En cada
simulacion se construyen las tablas de los 12 grupos, se eligen los 8 mejores
terceros, se asignan a los cruces de dieciseisavos respetando los grupos
permitidos y se resuelve todo el cuadro hasta la final, registrando hasta donde
llego cada seleccion.

Para que N grande sea viable:
  - Los goles esperados (mu) de los partidos de grupo pendientes se calculan una
    sola vez y se simulan de forma vectorizada en cada corrida.
  - Los cruces de eliminacion usan una cache (MuCache) porque el mismo
    emparejamiento se repite entre simulaciones.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from . import simulate as S
from . import io_load as IO


# Orden de profundidad alcanzada en el torneo.
STAGE_ORDER = {"group": 0, "R32": 1, "R16": 2, "QF": 3, "SF": 4, "F": 5, "W": 6}


class MuCache:
    """
    Cachea (mu_local, mu_visita, figura_local, figura_visita) por
    emparejamiento (local, visita, sede). build_mu es determinista con esos
    argumentos, por lo que cachear es exacto.
    """

    def __init__(self, params, teams, venues, cfg, players_by_team):
        self.params = params
        self.teams = teams
        self.venues = venues
        self.cfg = cfg
        self.pbt = players_by_team or {}
        self._cache = {}

    def get(self, home, away, venue):
        key = (home, away, venue)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        mu_h, mu_a, _ = S.build_mu(self.params, self.teams, self.venues, self.cfg,
                                   home, away, venue, self.pbt)
        sh = float(self.pbt.get(home, {}).get("star_rating", 0.5))
        sa = float(self.pbt.get(away, {}).get("star_rating", 0.5))
        val = (mu_h, mu_a, sh, sa)
        self._cache[key] = val
        return val


def simulate_winner_cached(rng, mucache: MuCache, home, away, venue):
    """
    Una realizacion de un partido de eliminacion usando mu cacheado.
    Incluye momento de figura y resuelve el empate con moneda ponderada por mu
    (proxy de prorroga y penales). Devuelve (ganador, perdedor).
    """
    mu_h, mu_a, sh, sa = mucache.get(home, away, venue)
    pv = mucache.cfg["player_variance"]
    gh = int(rng.poisson(mu_h))
    ga = int(rng.poisson(mu_a))
    if rng.random() < pv["star_event_base_prob"] * (0.5 + sh) * pv["star_goal_share"]:
        gh += 1
    if rng.random() < pv["star_event_base_prob"] * (0.5 + sa) * pv["star_goal_share"]:
        ga += 1
    if gh > ga:
        return home, away
    if ga > gh:
        return away, home
    p_home = mu_h / (mu_h + mu_a)
    return (home, away) if rng.random() < p_home else (away, home)


def _base_standings(teams, played):
    """
    Estadistica fija aportada por los partidos ya jugados.
    Devuelve dict code -> [pts, gd, gf].
    """
    stats = {c: [0, 0, 0] for c in teams["code"]}
    for h, a, gh, ga in played:
        _apply_result(stats, h, a, gh, ga)
    return stats


def _apply_result(stats, h, a, gh, ga):
    """Suma un resultado a la tabla (puntos, diferencia y goles a favor)."""
    stats[h][1] += gh - ga
    stats[a][1] += ga - gh
    stats[h][2] += gh
    stats[a][2] += ga
    if gh > ga:
        stats[h][0] += 3
    elif ga > gh:
        stats[a][0] += 3
    else:
        stats[h][0] += 1
        stats[a][0] += 1


def _order_group(codes, stats, jit):
    """
    Ordena un grupo por puntos, diferencia de goles, goles a favor y un
    desempate aleatorio reproducible. (El desempate por enfrentamiento directo
    de FIFA se omite; ver README.) Devuelve la lista ordenada de codigos.
    """
    return sorted(codes,
                  key=lambda c: (stats[c][0], stats[c][1], stats[c][2], jit[c]),
                  reverse=True)


def _assign_thirds(thirds_by_group, slots, rng):
    """
    Asigna los 8 mejores terceros a los cruces de dieciseisavos respetando el
    conjunto de grupos permitido de cada cruce (matching biyectivo por
    backtracking). Devuelve dict match_no -> code. Aproxima la tabla oficial de
    FIFA: encuentra una asignacion valida, no necesariamente la tabulada.
    """
    groups_avail = set(thirds_by_group.keys())
    # cruces ordenados por mas restrictivos primero (menos terceros compatibles)
    order = sorted(slots,
                   key=lambda s: len(s[1] & groups_avail))
    assignment = {}
    used = set()

    def backtrack(i):
        if i == len(order):
            return True
        match_no, allowed = order[i]
        cands = [g for g in (allowed & groups_avail) if g not in used]
        rng.shuffle(cands)
        for g in cands:
            used.add(g)
            assignment[match_no] = thirds_by_group[g]
            if backtrack(i + 1):
                return True
            used.discard(g)
            del assignment[match_no]
        return False

    if backtrack(0):
        return assignment
    # respaldo: asignacion directa si no hubo matching perfecto (no deberia pasar)
    leftover = list(thirds_by_group.values())
    rng.shuffle(leftover)
    return {slots[i][0]: leftover[i] for i in range(len(slots))}


def _resolve(token, table, third_assign, winners, losers, match_no):
    """
    Resuelve un slot del cuadro a un codigo de seleccion.
      "A1"/"B2" -> posicion del grupo (table[g][pos-1])
      "3:..."   -> tercero asignado a este cruce (third_assign[match_no])
      "Wnn"     -> ganador del partido nn
      "Lnn"     -> perdedor del partido nn
    Ojo: "L1"/"L2" son posiciones del Grupo L; "L101"/"L102" son perdedores. Se
    distinguen porque el numero de un partido de eliminacion es >= 73.
    """
    if token.startswith("3:"):
        return third_assign[match_no]
    head, rest = token[0], token[1:]
    if head in ("W", "L") and rest.isdigit() and int(rest) >= 73:
        return winners[int(rest)] if head == "W" else losers[int(rest)]
    return table[head][int(rest) - 1]


def simulate_once(rng, ctx):
    """
    Una simulacion completa del torneo.
    Devuelve (stage, won_group, positions):
      stage[code]      -> fase mas profunda alcanzada (clave de STAGE_ORDER)
      won_group        -> set de ganadores de grupo
      positions[code]  -> posicion final en su grupo (1..4)
    """
    teams = ctx["teams"]
    group_teams = ctx["group_teams"]
    codes = ctx["codes"]

    # 1) goles de los partidos de grupo pendientes (vectorizado)
    n = len(ctx["sch_mu_h"])
    gh = rng.poisson(ctx["sch_mu_h"])
    ga = rng.poisson(ctx["sch_mu_a"])
    pv = ctx["cfg"]["player_variance"]
    base = pv["star_event_base_prob"]
    share = pv["star_goal_share"]
    ev_h = rng.random(n) < base * (0.5 + ctx["sch_star_h"])
    ev_a = rng.random(n) < base * (0.5 + ctx["sch_star_a"])
    gh = gh + (ev_h & (rng.random(n) < share)).astype(int)
    ga = ga + (ev_a & (rng.random(n) < share)).astype(int)

    # 2) tabla de grupos: base fija + lo simulado
    stats = {c: ctx["base_stats"][c][:] for c in codes}
    sch_home = ctx["sch_home"]
    sch_away = ctx["sch_away"]
    for i in range(n):
        _apply_result(stats, sch_home[i], sch_away[i], int(gh[i]), int(ga[i]))

    jit = {c: rng.random() for c in codes}
    table = {}
    positions = {}
    won_group = set()
    thirds = []   # (pts, gd, gf, jit, group, code)
    for g, members in group_teams.items():
        ordered = _order_group(members, stats, jit)
        table[g] = ordered
        for pos, c in enumerate(ordered, start=1):
            positions[c] = pos
        won_group.add(ordered[0])
        t = ordered[2]
        thirds.append((stats[t][0], stats[t][1], stats[t][2], jit[t], g, t))

    # 3) 8 mejores terceros
    thirds.sort(key=lambda x: (x[0], x[1], x[2], x[3]), reverse=True)
    best = thirds[:8]
    thirds_by_group = {row[4]: row[5] for row in best}

    # 4) estado inicial de fase: clasificados llegan al menos a R32
    stage = {c: "group" for c in codes}
    for g, ordered in table.items():
        stage[ordered[0]] = "R32"
        stage[ordered[1]] = "R32"
    for row in best:
        stage[row[5]] = "R32"

    # 5) asignar terceros a los cruces y resolver el cuadro
    third_assign = _assign_thirds(thirds_by_group, ctx["third_slots"], rng)

    winners, losers = {}, {}
    mc = ctx["mucache"]
    for match_no, home_tok, away_tok, venue, reach in ctx["bracket_seq"]:
        h = _resolve(home_tok, table, third_assign, winners, losers, match_no)
        a = _resolve(away_tok, table, third_assign, winners, losers, match_no)
        w, l = simulate_winner_cached(rng, mc, h, a, venue)
        winners[match_no] = w
        losers[match_no] = l
        if reach is not None and STAGE_ORDER[reach] > STAGE_ORDER[stage[w]]:
            stage[w] = reach

    return stage, won_group, positions


def _build_bracket_seq(bracket):
    """
    Linealiza el cuadro en orden de juego. Cada entrada:
      (match_no, home_token, away_token, venue, fase_que_alcanza_el_ganador)
    El partido por el tercer puesto (103) no eleva fase: reach=None.
    """
    reach_by_round = {
        "round_of_32": "R16",
        "round_of_16": "QF",
        "quarter_finals": "SF",
        "semi_finals": "F",
        "third_place": None,
        "final": "W",
    }
    seq = []
    for rkey in ["round_of_32", "round_of_16", "quarter_finals",
                 "semi_finals", "third_place", "final"]:
        reach = reach_by_round[rkey]
        for match_no, spec in sorted(bracket[rkey].items()):
            seq.append((int(match_no), spec["home"], spec["away"],
                        spec["venue"], reach))
    return seq


def _third_slots(bracket):
    """Cruces de dieciseisavos que reciben un tercero, con sus grupos permitidos."""
    slots = []
    for match_no, spec in bracket["round_of_32"].items():
        tok = spec["away"]
        if tok.startswith("3:"):
            slots.append((int(match_no), set(tok[2:])))
    return slots


def run(params, teams, venues, fixtures, bracket, cfg,
        players_by_team=None, n=None, seed=None):
    """
    Corre n simulaciones del torneo y devuelve un DataFrame por seleccion con:
    p_advance, p_win_group, p_R16, p_QF, p_SF, p_final, p_champion y
    probabilidad de terminar 1o/2o/3o/4o de grupo (p_g1..p_g4).
    Ordenado por p_champion.
    """
    n = n or cfg["simulation"]["n_tournament"]
    seed = cfg["simulation"]["seed"] if seed is None else seed
    rng = np.random.default_rng(seed)

    codes = list(teams["code"])
    group_teams = {g: list(teams[teams["group"] == g]["code"])
                   for g in sorted(teams["group"].unique())}

    # partidos jugados (fijos) y pendientes (a simular)
    played, sch = [], []
    for _, r in fixtures.iterrows():
        if r["status"] == "played" and pd.notna(r["home_goals"]):
            played.append((r["home"], r["away"],
                           int(r["home_goals"]), int(r["away_goals"])))
        else:
            sch.append((r["home"], r["away"], r["venue"]))

    mucache = MuCache(params, teams, venues, cfg, players_by_team)

    # precomputo de mu de los partidos de grupo pendientes
    sch_home = [s[0] for s in sch]
    sch_away = [s[1] for s in sch]
    sch_mu_h = np.empty(len(sch))
    sch_mu_a = np.empty(len(sch))
    sch_star_h = np.empty(len(sch))
    sch_star_a = np.empty(len(sch))
    for i, (h, a, v) in enumerate(sch):
        mh, ma, sh, sa = mucache.get(h, a, v)
        sch_mu_h[i], sch_mu_a[i], sch_star_h[i], sch_star_a[i] = mh, ma, sh, sa

    ctx = dict(
        teams=teams, codes=codes, group_teams=group_teams, cfg=cfg,
        base_stats=_base_standings(teams, played),
        sch_home=sch_home, sch_away=sch_away,
        sch_mu_h=sch_mu_h, sch_mu_a=sch_mu_a,
        sch_star_h=sch_star_h, sch_star_a=sch_star_a,
        third_slots=_third_slots(bracket),
        bracket_seq=_build_bracket_seq(bracket),
        mucache=mucache,
    )

    # acumuladores
    adv = {c: 0 for c in codes}
    wg = {c: 0 for c in codes}
    r16 = {c: 0 for c in codes}
    qf = {c: 0 for c in codes}
    sf = {c: 0 for c in codes}
    fin = {c: 0 for c in codes}
    champ = {c: 0 for c in codes}
    pos_counts = {c: [0, 0, 0, 0] for c in codes}

    for _ in range(n):
        stage, won_group, positions = simulate_once(rng, ctx)
        for c in codes:
            s = STAGE_ORDER[stage[c]]
            if s >= 1:
                adv[c] += 1
            if s >= 2:
                r16[c] += 1
            if s >= 3:
                qf[c] += 1
            if s >= 4:
                sf[c] += 1
            if s >= 5:
                fin[c] += 1
            if s >= 6:
                champ[c] += 1
            pos_counts[c][positions[c] - 1] += 1
        for c in won_group:
            wg[c] += 1

    rows = []
    for c in codes:
        pc = pos_counts[c]
        rows.append(dict(
            code=c, name=teams.loc[c, "name_es"], group=teams.loc[c, "group"],
            p_advance=adv[c] / n, p_win_group=wg[c] / n,
            p_R16=r16[c] / n, p_QF=qf[c] / n, p_SF=sf[c] / n,
            p_final=fin[c] / n, p_champion=champ[c] / n,
            p_g1=pc[0] / n, p_g2=pc[1] / n, p_g3=pc[2] / n, p_g4=pc[3] / n,
        ))
    df = pd.DataFrame(rows).set_index("code")
    return df.sort_values("p_champion", ascending=False)
