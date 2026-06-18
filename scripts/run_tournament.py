"""
run_tournament.py
Corre muchas simulaciones del torneo completo y reporta, por seleccion, la
probabilidad de avanzar, ganar su grupo y llegar a cada ronda hasta el titulo.

    python scripts/run_tournament.py
    python scripts/run_tournament.py --n 50000 --seed 7
    python scripts/run_tournament.py --groups A,B,H     # ademas, proyeccion de grupos
    python scripts/run_tournament.py --save artifacts/torneo.csv

Usa el modelo ajustado (artifacts/params.json). Si no existe, lo ajusta solo.
Como solo simula los partidos pendientes, el pronostico se afina conforme
registras resultados (ver scripts/update.py).
"""
from __future__ import annotations
import argparse
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import pandas as pd
from wc2026 import io_load as IO
from wc2026 import model as M
from wc2026 import tournament as T
from wc2026 import report as RP


def _players_by_team(players):
    return {r["team"]: r.to_dict() for _, r in players.iterrows()}


def main():
    ap = argparse.ArgumentParser(description="Simula el torneo completo.")
    ap.add_argument("--n", type=int, default=None, help="Numero de simulaciones.")
    ap.add_argument("--seed", type=int, default=None, help="Semilla.")
    ap.add_argument("--top", type=int, default=16, help="Cuantas selecciones mostrar.")
    ap.add_argument("--groups", default=None,
                    help="Grupos para proyeccion detallada, ej. A,B,H")
    ap.add_argument("--save", default=None, help="Ruta CSV para guardar la tabla completa.")
    args = ap.parse_args()

    cfg = IO.load_settings()
    teams = IO.load_teams()
    venues = IO.load_venues()
    players = IO.load_players()
    fixtures = IO.load_group_fixtures()
    bracket = IO.load_bracket()

    try:
        params = M.load_params()
    except FileNotFoundError:
        print("No hay modelo ajustado; ajustando ahora...")
        matches = IO.played_matches_for_fit()
        as_of = matches["date"].max() if len(matches) else pd.Timestamp.today()
        params = M.fit(teams, matches, cfg, as_of)
        M.save_params(params)

    n = args.n or cfg["simulation"]["n_tournament"]
    print(f"Simulando el torneo {n:,} veces...")
    df = T.run(params, teams, venues, fixtures, bracket, cfg,
               players_by_team=_players_by_team(players), n=args.n, seed=args.seed)

    print()
    print(RP.tournament_report(df, top=args.top))

    if args.groups:
        for g in [s.strip().upper() for s in args.groups.split(",")]:
            print()
            print(RP.group_projection(df, g))

    if args.save:
        df.to_csv(args.save)
        print(f"\nTabla completa guardada en: {args.save}")


if __name__ == "__main__":
    main()
