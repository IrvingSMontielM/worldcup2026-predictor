"""
sync.py
Orquesta el ciclo en vivo de principio a fin:
  1. Consulta la API y escribe los resultados finalizados en fixtures_group.csv.
  2. Reajusta el modelo (fit) con los partidos disputados.
  3. Simula el torneo completo.
  4. Predice los partidos pendientes.
  5. Publica salidas tipo dashboard en live/ (torneo.csv, predicciones.csv,
     resumen.md), pensadas para versionarse y verse directo en GitHub.

    python scripts/sync.py                         # usa API_FOOTBALL_KEY del entorno
    python scripts/sync.py --provider opensource   # sin key, mejor esfuerzo
    python scripts/sync.py --provider none --force  # sin ingesta, solo recalcula

Robusto: si la ingesta falla (sin red o sin key), avisa y recalcula con lo que
ya esta en el CSV, de modo que las salidas siempre se refrescan.
"""
from __future__ import annotations
import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import pandas as pd
from wc2026 import io_load as IO
from wc2026 import model as M
from wc2026 import tournament as T
from wc2026 import simulate as SIM
from wc2026 import report as RP
from wc2026 import live as LV
from wc2026 import picks as PK
from wc2026 import odds as OD

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE = os.path.join(ROOT, "live")


def _players_by_team(players):
    return {r["team"]: r.to_dict() for _, r in players.iterrows()}


def _market_row(market, home, away):
    if not len(market):
        return None
    hit = market[(market["home"] == home) & (market["away"] == away)]
    return hit.iloc[0] if len(hit) else None


def ingest(provider, season):
    """Capa 1: consulta la API y escribe resultados. Devuelve la lista aplicada."""
    teams = IO.load_teams()
    crosswalk = LV.build_crosswalk(teams)
    valid = set(teams["code"])
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    fixtures_path = os.path.join(IO.DATA, "fixtures_group.csv")
    try:
        results = LV.fetch_results(provider, crosswalk, valid, api_key, season)
    except Exception as e:  # red caida, key invalida, esquema cambiado
        print(f"  Ingesta omitida ({type(e).__name__}): {e}")
        return []
    applied = LV.apply_results(results, fixtures_path)
    print(f"  Partidos finalizados recibidos: {len(results)}.  "
          f"Nuevos o corregidos: {len(applied)}.")
    for mn, h, a, gh, ga in applied:
        print(f"    #{mn}: {h} {gh}-{ga} {a}")
    return applied


def refit():
    """Capa 2: reajusta el modelo y guarda params.json."""
    cfg = IO.load_settings()
    teams = IO.load_teams()
    matches = IO.played_matches_for_fit()
    as_of = matches["date"].max() if len(matches) else pd.Timestamp.today()
    params = M.fit(teams, matches, cfg, as_of)
    M.save_params(params)
    print(f"  Modelo reajustado con {params['n_matches']} partidos "
          f"(corte {pd.Timestamp(as_of).date()}).")
    return params


def simulate_tournament(params, n, seed):
    """Capa 3: simula el torneo y guarda live/torneo.csv."""
    cfg = IO.load_settings()
    teams = IO.load_teams()
    venues = IO.load_venues()
    players = IO.load_players()
    fixtures = IO.load_group_fixtures()
    bracket = IO.load_bracket()
    n = n or cfg["simulation"]["n_tournament"]
    df = T.run(params, teams, venues, fixtures, bracket, cfg,
               players_by_team=_players_by_team(players), n=n, seed=seed)
    os.makedirs(LIVE, exist_ok=True)
    df.round(4).to_csv(os.path.join(LIVE, "torneo.csv"))
    print(f"  Torneo simulado {n:,} veces.  "
          f"Favorito: {df.iloc[0]['name']} ({100 * df.iloc[0]['p_champion']:.1f}%).")
    return df


def predict_upcoming(params, n_sim, limit=None):
    """Capa 4: predice los partidos pendientes y guarda live/predicciones.csv."""
    cfg = IO.load_settings()
    teams = IO.load_teams()
    venues = IO.load_venues()
    players = IO.load_players()
    market = IO.load_market_odds()
    fixtures = IO.load_group_fixtures()
    pbt = _players_by_team(players)

    pend = fixtures[fixtures["status"] == "scheduled"].sort_values("date")
    if limit:
        pend = pend.head(limit)

    rows, preds_full = [], []
    for _, m in pend.iterrows():
        pred = SIM.predict_match(
            params, teams, venues, cfg, m["home"], m["away"], m["venue"],
            players_by_team=pbt, market_row=_market_row(market, m["home"], m["away"]),
            n_sim=n_sim)
        pred["match_no"] = int(m["match_no"])
        pred["date"] = str(m["date"])[:10]
        pred["group"] = m["group"]
        preds_full.append(pred)
        p, gm, mb = pred["probs"], pred["markets_goals"], pred["markets_aux"]
        rows.append(dict(
            match_no=int(m["match_no"]), date=str(m["date"])[:10], group=m["group"],
            home=m["home"], away=m["away"], venue=m["venue"],
            p_home=round(p["p_home"], 4), p_draw=round(p["p_draw"], 4),
            p_away=round(p["p_away"], 4),
            xg_home=round(gm["exp_goals_home"], 2), xg_away=round(gm["exp_goals_away"], 2),
            p_over25=round(gm["p_over25"], 4), p_btts=round(gm["p_btts"], 4),
            corners_home=mb["corners_home"], corners_away=mb["corners_away"],
            cards_home=mb["cards_home"], cards_away=mb["cards_away"]))
    out = pd.DataFrame(rows)
    os.makedirs(LIVE, exist_ok=True)
    out.to_csv(os.path.join(LIVE, "predicciones.csv"), index=False)
    print(f"  Predicciones generadas para {len(out)} partidos pendientes.")
    return out, preds_full


def fetch_odds():
    """Capa opcional: descarga momios de mercado si hay ODDS_API_KEY."""
    if not os.environ.get("ODDS_API_KEY"):
        print("  Sin ODDS_API_KEY; los picks saldran solo del modelo.")
        return
    try:
        counts = OD.fetch_and_write(IO.load_teams(), IO.load_group_fixtures())
        print(f"  Momios cargados: {counts['odds_1x2']} de 1X2, "
              f"{counts['totals']} de over/under.")
    except Exception as e:
        print(f"  Ingesta de momios omitida ({type(e).__name__}): {e}")


def generate_picks(preds_full):
    """Capa 6: arma los picks y los publica en live/picks.csv y live/picks.md."""
    import datetime as dt
    teams = IO.load_teams()
    market = IO.load_market_odds()
    totals = IO.load_market_totals()

    def market_lookup(h, a):
        if not len(market):
            return None
        hit = market[(market["home"] == h) & (market["away"] == a)]
        return hit.iloc[0] if len(hit) else None

    def totals_lookup(h, a):
        if not len(totals):
            return None
        hit = totals[(totals["home"] == h) & (totals["away"] == a)]
        return hit.iloc[0] if len(hit) else None

    df = PK.build_table(preds_full, teams, market_lookup, totals_lookup)
    os.makedirs(LIVE, exist_ok=True)
    df.drop(columns=["_score", "_rationale"]).to_csv(
        os.path.join(LIVE, "picks.csv"), index=False)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(os.path.join(LIVE, "picks.md"), "w", encoding="utf-8") as f:
        f.write(PK.render_md(df, now))
    if len(df):
        top = df.iloc[0]
        print(f"  Picks generados.  Pick del dia: {top['partido']} -> "
              f"{top['pick_principal']} ({top['pick_prob']*100:.0f}%).")
    return df


def write_summary(df, preds, fixtures):
    """Capa 5: resumen en markdown que se renderiza en GitHub."""
    played = int((fixtures["status"] == "played").sum())
    sched = int((fixtures["status"] == "scheduled").sum())
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    L = []
    L.append("# Estado del pronostico (en vivo)\n")
    L.append(f"Ultima actualizacion: **{now}**  \n")
    L.append(f"Partidos disputados: **{played}** de 72 en fase de grupos. "
             f"Pendientes: **{sched}**.\n")

    L.append("\n## Candidatos al titulo (top 10)\n")
    L.append("| Seleccion | Grupo | Campeon | Final | Avanza |")
    L.append("|---|---|---:|---:|---:|")
    for _, r in df.head(10).iterrows():
        L.append(f"| {r['name']} | {r['group']} | {100 * r['p_champion']:.1f}% "
                 f"| {100 * r['p_final']:.1f}% | {100 * r['p_advance']:.1f}% |")

    if len(preds):
        L.append("\n## Proximos partidos\n")
        L.append("| Fecha | Grupo | Partido | Local | Empate | Visita | Goles esp. |")
        L.append("|---|---|---|---:|---:|---:|:--:|")
        for _, p in preds.head(12).iterrows():
            L.append(f"| {p['date']} | {p['group']} | {p['home']} vs {p['away']} "
                     f"| {100 * p['p_home']:.0f}% | {100 * p['p_draw']:.0f}% "
                     f"| {100 * p['p_away']:.0f}% | {p['xg_home']:.1f}-{p['xg_away']:.1f} |")

    L.append("\n---\n")
    L.append("Generado automaticamente por `scripts/sync.py`. "
             "Las probabilidades se afinan conforme se registran resultados.\n")

    os.makedirs(LIVE, exist_ok=True)
    with open(os.path.join(LIVE, "resumen.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("  Resumen escrito en live/resumen.md")


def main():
    ap = argparse.ArgumentParser(description="Ciclo en vivo: ingesta, ajuste, simulacion.")
    ap.add_argument("--provider", default=os.environ.get("WC_PROVIDER", "apifootball"),
                    choices=["apifootball", "opensource", "none"],
                    help="Fuente de resultados.")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--n", type=int, default=None, help="Simulaciones de torneo.")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--pred-n", type=int, default=3000,
                    help="Simulaciones por partido pendiente.")
    ap.add_argument("--force", action="store_true",
                    help="Recalcula aunque no haya resultados nuevos.")
    args = ap.parse_args()

    print(f"[1/6] Ingesta de resultados (proveedor: {args.provider})")
    applied = ingest(args.provider, args.season)

    params_exist = os.path.exists(os.path.join(IO.ARTIFACTS, "params.json"))
    if not applied and not args.force and params_exist:
        print("Sin resultados nuevos. Usa --force para recalcular de todos modos.")
        return

    print("[2/6] Reajuste del modelo")
    params = refit()

    print("[3/6] Simulacion del torneo")
    df = simulate_tournament(params, args.n, args.seed)

    print("[4/6] Ingesta de momios de mercado (opcional)")
    fetch_odds()

    print("[5/6] Prediccion de partidos pendientes")
    preds_df, preds_full = predict_upcoming(params, args.pred_n)

    print("[6/6] Picks y resumen")
    generate_picks(preds_full)
    write_summary(df, preds_df, IO.load_group_fixtures())

    print("Listo. Salidas en live/: torneo.csv, predicciones.csv, "
          "picks.csv, picks.md, resumen.md")


if __name__ == "__main__":
    main()
