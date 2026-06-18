"""
predict.py
Prediccion completa de un partido: 1X2, goles, marcadores, tiros de esquina,
tiros, tarjetas, contexto y una sugerencia en lenguaje natural.

    python scripts/predict.py BRA HAI PHI
    python scripts/predict.py MEX KOR GDL --n 50000

Codigos de equipo y de sede: ver data/teams.csv y data/venues.csv.
Si el partido tiene momios en data/market_odds.csv, se mezclan automaticamente.
"""
from __future__ import annotations
import argparse
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from wc2026 import io_load as IO
from wc2026 import model as M
from wc2026 import simulate as SIM
from wc2026 import report as RP


def _players_by_team(players):
    return {r["team"]: r.to_dict() for _, r in players.iterrows()}


def _market_row(market, home, away):
    if not len(market):
        return None
    hit = market[(market["home"] == home) & (market["away"] == away)]
    return hit.iloc[0] if len(hit) else None


def main():
    ap = argparse.ArgumentParser(description="Predice un partido.")
    ap.add_argument("home", help="Codigo del equipo local (ej. BRA).")
    ap.add_argument("away", help="Codigo del equipo visitante (ej. HAI).")
    ap.add_argument("venue", help="Codigo de la sede (ej. PHI).")
    ap.add_argument("--n", type=int, default=None, help="Numero de simulaciones.")
    ap.add_argument("--seed", type=int, default=None, help="Semilla.")
    args = ap.parse_args()

    cfg = IO.load_settings()
    teams = IO.load_teams()
    venues = IO.load_venues()
    players = IO.load_players()
    market = IO.load_market_odds()

    for code in (args.home, args.away):
        if code not in teams.index:
            sys.exit(f"Codigo de equipo desconocido: {code}. Ver data/teams.csv")
    if args.venue not in venues.index:
        sys.exit(f"Codigo de sede desconocido: {args.venue}. Ver data/venues.csv")

    try:
        params = M.load_params()
    except FileNotFoundError:
        sys.exit("No hay modelo ajustado. Corre primero: python scripts/fit.py")

    pred = SIM.predict_match(
        params, teams, venues, cfg, args.home, args.away, args.venue,
        players_by_team=_players_by_team(players),
        market_row=_market_row(market, args.home, args.away),
        n_sim=args.n, seed=args.seed)

    print(RP.match_report(pred, teams))


if __name__ == "__main__":
    main()
