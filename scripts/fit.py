"""
fit.py
Ajusta el modelo de goles con los partidos disputados (historico + Mundial) y
guarda los parametros en artifacts/params.json.

Ejecutar despues de build_data.py y cada vez que registres nuevos resultados:
    python scripts/fit.py
    python scripts/fit.py --as-of 2026-06-20
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


def main():
    ap = argparse.ArgumentParser(description="Ajusta el modelo de goles.")
    ap.add_argument("--as-of", default=None,
                    help="Fecha de corte YYYY-MM-DD (por defecto, ultimo partido jugado).")
    args = ap.parse_args()

    cfg = IO.load_settings()
    teams = IO.load_teams()
    matches = IO.played_matches_for_fit(
        pd.Timestamp(args.as_of) if args.as_of else None)

    as_of = (pd.Timestamp(args.as_of) if args.as_of
             else (matches["date"].max() if len(matches) else pd.Timestamp.today()))

    params = M.fit(teams, matches, cfg, as_of)
    path = M.save_params(params)

    print(f"Modelo ajustado con {params['n_matches']} partidos.  "
          f"Corte: {pd.Timestamp(as_of).date()}")
    print(f"intercepto={params['intercept']:.3f}  "
          f"ventaja_local={params['home_adv']:.3f}  rho={params['rho']:.3f}  "
          f"convergio={params.get('converged', True)}")
    print(f"Parametros guardados en: {path}")

    rating = pd.Series(params["rating"]).sort_values(ascending=False)
    print("\nTop 10 por rating (FIFA + Elo):")
    for c in rating.head(10).index:
        print(f"  {teams.loc[c, 'name_es']:<22} rating={rating[c]:+.2f}  "
              f"atk={params['atk'][c]:+.2f}  dfn={params['dfn'][c]:+.2f}")


if __name__ == "__main__":
    main()
