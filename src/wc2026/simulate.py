"""
simulate.py
Motor de simulacion a nivel de partido.

build_mu()      -> goles esperados ajustados por contexto, estilo, forma, lesion
                   y dependencia a balon parado.
predict_match() -> prediccion analitica completa (1X2, marcadores, mercados) y
                   ademas corre N simulaciones para construir una narrativa
                   ("que esperar") incorporando momentos de figura.
simulate_winner() -> usado por el torneo en fases de eliminacion (con prorroga
                     y penales si hace falta).
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from . import model as M
from . import context as C
from . import markets as MK
from . import blend as B


def _player_adjust(team_code, players_by_team, cfg):
    """Multiplicador por forma y lesion de la figura del equipo."""
    pv = cfg["player_variance"]
    row = players_by_team.get(team_code)
    if row is None:
        return 1.0, 0.5
    form = float(row.get("form", 1.0) or 1.0)
    star = float(row.get("star_rating", 0.5) or 0.5)
    injury = str(row.get("injury", "") or "").strip().lower()
    mult = 1.0 + pv["form_span"] * (form - 1.0)
    if injury == "doubtful":
        mult *= 1.0 - pv["injury_doubtful_penalty"]
    elif injury == "out":
        mult *= 1.0 - pv["injury_out_penalty"]
    return mult, star


def build_mu(params, teams, venues, cfg, home, away, venue,
             players_by_team=None, travel_home_km=0.0, travel_away_km=0.0,
             attendance=None, neutral_ok=True):
    """
    Devuelve (mu_home, mu_away, ctx_info) ya ajustados.
    Encadena: Dixon-Coles -> ventaja localia -> contexto -> estilo balon parado
    -> forma/lesion de la figura.
    """
    players_by_team = players_by_team or {}
    vrow = venues.loc[venue]

    mh_ctx, ma_ctx, adv_h, adv_a, info = C.context_multipliers(
        home, away, vrow, teams, cfg, travel_home_km, travel_away_km, attendance)

    mu_h, mu_a = M.expected_goals(params, home, away, adv_home=adv_h, adv_away=adv_a)
    mu_h *= mh_ctx
    mu_a *= ma_ctx

    # balon parado: parte del ataque que no depende de la defensa rival en juego
    sp_h = teams.loc[home, "set_piece"]
    sp_a = teams.loc[away, "set_piece"]
    mu_h *= 1.0 + 0.10 * (sp_h - 0.30)
    mu_a *= 1.0 + 0.10 * (sp_a - 0.30)

    # forma y lesion de la figura
    fm_h, star_h = _player_adjust(home, players_by_team, cfg)
    fm_a, star_a = _player_adjust(away, players_by_team, cfg)
    mu_h *= fm_h
    mu_a *= fm_a

    info["star_home"] = star_h
    info["star_away"] = star_a
    info["mu_home"] = round(mu_h, 3)
    info["mu_away"] = round(mu_a, 3)
    return max(mu_h, 0.05), max(mu_a, 0.05), info


def _simulate_scores(rng, mu_h, mu_a, star_h, star_a, n, cfg):
    """
    N realizaciones de goles. Incluye 'momento de figura': con cierta
    probabilidad un equipo suma un gol extra inesperado (individualidad).
    Devuelve arrays (gh, ga) y un contador de cuantas veces decidio la figura.
    """
    pv = cfg["player_variance"]
    gh = rng.poisson(mu_h, n)
    ga = rng.poisson(mu_a, n)

    p_star_h = pv["star_event_base_prob"] * (0.5 + star_h)
    p_star_a = pv["star_event_base_prob"] * (0.5 + star_a)
    ev_h = rng.random(n) < p_star_h
    ev_a = rng.random(n) < p_star_a
    add_h = ev_h & (rng.random(n) < pv["star_goal_share"])
    add_a = ev_a & (rng.random(n) < pv["star_goal_share"])

    before_diff = gh - ga
    gh = gh + add_h.astype(int)
    ga = ga + add_a.astype(int)
    after_diff = gh - ga
    # la figura "decide" si cambia el signo del resultado
    decided = np.sign(before_diff) != np.sign(after_diff)
    return gh, ga, int(decided.sum())


def predict_match(params, teams, venues, cfg, home, away, venue,
                  players_by_team=None, market_row=None,
                  travel_home_km=0.0, travel_away_km=0.0, attendance=None,
                  n_sim=None, seed=None):
    """Prediccion completa de un partido (analitica + simulada + mezcla con mercado)."""
    n_sim = n_sim or cfg["simulation"]["n_match"]
    seed = cfg["simulation"]["seed"] if seed is None else seed
    rng = np.random.default_rng(seed)

    mu_h, mu_a, info = build_mu(params, teams, venues, cfg, home, away, venue,
                                players_by_team, travel_home_km, travel_away_km,
                                attendance)

    # mercados de goles analiticos
    grid = M.score_grid(mu_h, mu_a, params["rho"], cfg["model"]["max_goals_grid"])
    gm = M.grid_markets(grid)
    model_probs = dict(p_home=gm["p_home"], p_draw=gm["p_draw"], p_away=gm["p_away"])

    # mezcla con mercado
    final_probs, used_market = B.blend_1x2(model_probs, market_row, cfg["blend"]["w_market"])

    # mercados auxiliares
    mb = MK.market_block(params, teams, cfg, home, away, mu_h, mu_a, gm["p_draw"])

    # simulaciones para narrativa
    gh, ga, decided = _simulate_scores(rng, mu_h, mu_a,
                                       info["star_home"], info["star_away"], n_sim, cfg)
    sim = dict(
        p_home=float((gh > ga).mean()), p_draw=float((gh == ga).mean()),
        p_away=float((gh < ga).mean()),
        avg_goals=float((gh + ga).mean()),
        star_decided_pct=round(100.0 * decided / n_sim, 1),
        clean_sheet_home=float((ga == 0).mean()),
        clean_sheet_away=float((gh == 0).mean()),
    )

    return dict(
        home=home, away=away, venue=venue, venue_name=venues.loc[venue, "name_es"],
        mu_home=round(mu_h, 3), mu_away=round(mu_a, 3),
        probs=final_probs, model_probs=model_probs, used_market=used_market,
        markets_goals=gm, markets_aux=mb, context=info, sim=sim, n_sim=n_sim,
    )


def simulate_winner(rng, params, teams, venues, cfg, home, away, venue,
                    players_by_team=None, allow_draw=False):
    """
    Una simulacion de un partido. Si allow_draw=False (eliminacion) resuelve el
    empate con una moneda ponderada por la fuerza (prorroga + penales aproximados).
    Devuelve (ganador, gh, ga).
    """
    mu_h, mu_a, _ = build_mu(params, teams, venues, cfg, home, away, venue, players_by_team)
    pv = cfg["player_variance"]
    gh = int(rng.poisson(mu_h))
    ga = int(rng.poisson(mu_a))
    # momento de figura
    sh = players_by_team.get(home, {}).get("star_rating", 0.5) if players_by_team else 0.5
    sa = players_by_team.get(away, {}).get("star_rating", 0.5) if players_by_team else 0.5
    if rng.random() < pv["star_event_base_prob"] * (0.5 + float(sh)) * pv["star_goal_share"]:
        gh += 1
    if rng.random() < pv["star_event_base_prob"] * (0.5 + float(sa)) * pv["star_goal_share"]:
        ga += 1

    if gh > ga:
        return home, gh, ga
    if ga > gh:
        return away, gh, ga
    if allow_draw:
        return None, gh, ga
    # desempate: probabilidad proporcional a goles esperados (prorroga/penales)
    p_home = mu_h / (mu_h + mu_a)
    return (home if rng.random() < p_home else away), gh, ga
