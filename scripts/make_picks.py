"""
make_picks.py
Genera los picks de apuesta de los partidos pendientes usando el modelo ya
ajustado, sin correr todo el ciclo de sincronizacion. Escribe live/picks.csv y
live/picks.md y muestra el pick del dia.

    python scripts/make_picks.py
    python scripts/make_picks.py --pred-n 8000 --limit 12

Requiere haber corrido antes: python scripts/fit.py
Si hay momios en data/market_odds.csv o data/market_totals.csv, calcula el valor.
"""
from __future__ import annotations
import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from wc2026 import io_load as IO
from wc2026 import model as M
from wc2026 import simulate as SIM
from wc2026 import picks as PK

LIVE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "live")


def main():
    ap = argparse.ArgumentParser(description="Genera picks de los partidos pendientes.")
    ap.add_argument("--pred-n", type=int, default=4000, help="Simulaciones por partido.")
    ap.add_argument("--limit", type=int, default=None, help="Maximo de partidos.")
    args = ap.parse_args()

    cfg = IO.load_settings()
    teams = IO.load_teams()
    venues = IO.load_venues()
    players = IO.load_players()
    fixtures = IO.load_group_fixtures()
    market = IO.load_market_odds()
    totals = IO.load_market_totals()

    try:
        params = M.load_params()
    except FileNotFoundError:
        sys.exit("No hay modelo ajustado. Corre primero: python scripts/fit.py")

    pbt = {r["team"]: r.to_dict() for _, r in players.iterrows()}

    def mr(h, a):
        if not len(market):
            return None
        hit = market[(market["home"] == h) & (market["away"] == a)]
        return hit.iloc[0] if len(hit) else None

    pend = fixtures[fixtures["status"] == "scheduled"].sort_values("date")
    if args.limit:
        pend = pend.head(args.limit)

    preds = []
    for _, m in pend.iterrows():
        pred = SIM.predict_match(params, teams, venues, cfg, m["home"], m["away"],
                                 m["venue"], players_by_team=pbt,
                                 market_row=mr(m["home"], m["away"]), n_sim=args.pred_n)
        pred["match_no"], pred["date"], pred["group"] = (
            int(m["match_no"]), str(m["date"])[:10], m["group"])
        preds.append(pred)

    def market_lookup(h, a):
        return mr(h, a)

    def totals_lookup(h, a):
        if not len(totals):
            return None
        hit = totals[(totals["home"] == h) & (totals["away"] == a)]
        return hit.iloc[0] if len(hit) else None

    df = PK.build_table(preds, teams, market_lookup, totals_lookup)
    os.makedirs(LIVE, exist_ok=True)
    df.drop(columns=["_score", "_rationale"]).to_csv(
        os.path.join(LIVE, "picks.csv"), index=False)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(os.path.join(LIVE, "picks.md"), "w", encoding="utf-8") as f:
        f.write(PK.render_md(df, now))

    if len(df):
        top = df.iloc[0]
        print(f"Pick del dia: {top['partido']} -> {top['pick_principal']} "
              f"({top['pick_prob']*100:.0f}%, {top['confianza'].lower()})")
        print(f"Picks de {len(df)} partidos en live/picks.csv y live/picks.md")


if __name__ == "__main__":
    main()
