"""
update.py
Registra el resultado real de un partido de grupos para volver dinamico el
modelo. Tras actualizar, vuelve a ajustar y a simular.

    python scripts/update.py 24 2 1      # partido 24 termino 2-1
    python scripts/update.py --list      # lista partidos pendientes

Flujo recomendado tras cada jornada:
    python scripts/update.py <match_no> <goles_local> <goles_visita>
    python scripts/fit.py
    python scripts/run_tournament.py
"""
from __future__ import annotations
import argparse
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import pandas as pd
from wc2026 import io_load as IO


def main():
    ap = argparse.ArgumentParser(description="Registra un resultado de grupos.")
    ap.add_argument("match_no", nargs="?", type=int, help="Numero de partido (1-72).")
    ap.add_argument("home_goals", nargs="?", type=int, help="Goles del local.")
    ap.add_argument("away_goals", nargs="?", type=int, help="Goles del visitante.")
    ap.add_argument("--list", action="store_true", help="Lista partidos pendientes.")
    args = ap.parse_args()

    path = os.path.join(IO.DATA, "fixtures_group.csv")
    df = pd.read_csv(path)

    if args.list:
        pend = df[df["status"] == "scheduled"]
        print(f"Partidos pendientes: {len(pend)}")
        for _, r in pend.iterrows():
            print(f"  #{int(r['match_no']):>2}  {r['date']}  Gpo {r['group']}  "
                  f"{r['home']} vs {r['away']}  @ {r['venue']}")
        return

    if args.match_no is None or args.home_goals is None or args.away_goals is None:
        sys.exit("Uso: python scripts/update.py <match_no> <goles_local> <goles_visita>"
                 "   (o --list)")

    mask = df["match_no"] == args.match_no
    if not mask.any():
        sys.exit(f"No existe el partido #{args.match_no}.")

    row = df[mask].iloc[0]
    df.loc[mask, "home_goals"] = args.home_goals
    df.loc[mask, "away_goals"] = args.away_goals
    df.loc[mask, "status"] = "played"
    df.to_csv(path, index=False)

    print(f"Registrado #{args.match_no}: {row['home']} {args.home_goals}-"
          f"{args.away_goals} {row['away']} (Gpo {row['group']}).")
    print("Ahora corre:  python scripts/fit.py  &&  python scripts/run_tournament.py")


if __name__ == "__main__":
    main()
