"""
io_load.py
Carga de configuracion y datos. Centraliza todas las rutas y entrega
estructuras listas para el resto de los modulos.
"""
from __future__ import annotations
import os
import yaml
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data")
CONFIG = os.path.join(ROOT, "config")
ARTIFACTS = os.path.join(ROOT, "artifacts")


def load_settings() -> dict:
    with open(os.path.join(CONFIG, "settings.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_bracket() -> dict:
    with open(os.path.join(DATA, "bracket.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_teams() -> pd.DataFrame:
    df = pd.read_csv(os.path.join(DATA, "teams.csv"))
    return df.set_index("code", drop=False)


def load_venues() -> pd.DataFrame:
    df = pd.read_csv(os.path.join(DATA, "venues.csv"))
    return df.set_index("code", drop=False)


def load_group_fixtures() -> pd.DataFrame:
    df = pd.read_csv(os.path.join(DATA, "fixtures_group.csv"))
    df["date"] = pd.to_datetime(df["date"])
    for c in ("home_goals", "away_goals"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def load_history() -> pd.DataFrame:
    path = os.path.join(DATA, "matches_history.csv")
    df = pd.read_csv(path)
    if len(df):
        df["date"] = pd.to_datetime(df["date"])
        for c in ("home_goals", "away_goals"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def load_players() -> pd.DataFrame:
    return pd.read_csv(os.path.join(DATA, "players.csv"))


def load_market_odds() -> pd.DataFrame:
    return pd.read_csv(os.path.join(DATA, "market_odds.csv"))


def load_market_totals() -> pd.DataFrame:
    path = os.path.join(DATA, "market_totals.csv")
    if not os.path.exists(path):
        return pd.DataFrame(columns=["match_no", "home", "away", "p_over25", "source"])
    return pd.read_csv(path)


def played_matches_for_fit(as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    """
    Devuelve todos los partidos con marcador (historico + grupos jugados)
    en un formato unico: date, home, away, home_goals, away_goals, home_adv.
    home_adv = 1 si el equipo local tuvo ventaja real de localia.
    """
    teams = load_teams()
    venues = load_venues()

    # Grupos jugados
    g = load_group_fixtures()
    g = g[g["status"] == "played"].copy()
    rows = []
    for _, r in g.iterrows():
        vcountry = venues.loc[r["venue"], "country"]
        # ventaja de localia real solo si el local es anfitrion en su pais
        adv = 1 if (teams.loc[r["home"], "host"] == 1 and
                    teams.loc[r["home"], "code"] == r["home"] and
                    _host_country(r["home"]) == vcountry) else 0
        rows.append((r["date"], r["home"], r["away"],
                     r["home_goals"], r["away_goals"], adv, "WC2026"))

    # Historico aportado por el usuario
    h = load_history()
    for _, r in h.iterrows():
        rows.append((r["date"], r["home"], r["away"],
                     r["home_goals"], r["away_goals"],
                     int(r.get("home_adv", 0) or 0), r.get("competition", "hist")))

    out = pd.DataFrame(rows, columns=["date", "home", "away",
                                      "home_goals", "away_goals", "home_adv", "competition"])
    if as_of is not None and len(out):
        out = out[out["date"] <= as_of]
    return out.dropna(subset=["home_goals", "away_goals"]).reset_index(drop=True)


def _host_country(team_code: str) -> str:
    return {"MEX": "MEX", "USA": "USA", "CAN": "CAN"}.get(team_code, "")
