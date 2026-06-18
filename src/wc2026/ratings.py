"""
ratings.py
Calidad de cada seleccion combinando ranking FIFA (prior estatico) y un Elo
dinamico que se actualiza con los resultados ya disputados. El Elo incorpora
margen de victoria y calidad del rival de forma natural.
"""
from __future__ import annotations
import math
import numpy as np
import pandas as pd


def temporal_weight(dates: pd.Series, as_of: pd.Timestamp, half_life_days: float) -> np.ndarray:
    """Peso exponencial: los partidos recientes pesan mas. peso = exp(-xi*dias)."""
    xi = math.log(2.0) / float(half_life_days)
    days = (as_of - dates).dt.days.clip(lower=0).to_numpy(dtype=float)
    return np.exp(-xi * days)


def seed_elo(teams: pd.DataFrame, scale: float) -> dict:
    """Elo inicial a partir de los puntos FIFA centrados en 1500."""
    mean_pts = teams["fifa_points"].mean()
    return {c: 1500.0 + (p - mean_pts) * scale
            for c, p in zip(teams["code"], teams["fifa_points"])}


def _mov_multiplier(goal_diff: int, elo_diff: float) -> float:
    """Multiplicador por margen de victoria (formula tipo World Football Elo)."""
    gd = abs(goal_diff)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11.0 + gd) / 8.0


def update_elo(teams: pd.DataFrame, matches: pd.DataFrame, cfg: dict,
               as_of: pd.Timestamp) -> dict:
    """
    Actualiza el Elo recorriendo los partidos en orden cronologico.
    Aplica ventaja de localia y margen de victoria.
    """
    elo = seed_elo(teams, cfg["ratings"]["elo_scale"])
    k = cfg["ratings"]["elo_k"]
    use_mov = cfg["ratings"]["elo_mov"]
    home_bonus = cfg["ratings"]["home_elo_bonus"]

    m = matches.sort_values("date")
    for _, r in m.iterrows():
        h, a = r["home"], r["away"]
        if h not in elo or a not in elo:
            continue
        rh = elo[h] + (home_bonus if r["home_adv"] == 1 else 0.0)
        ra = elo[a]
        exp_h = 1.0 / (1.0 + 10 ** ((ra - rh) / 400.0))
        gh, ga = int(r["home_goals"]), int(r["away_goals"])
        score_h = 1.0 if gh > ga else (0.5 if gh == ga else 0.0)
        mult = _mov_multiplier(gh - ga, rh - ra) if use_mov else 1.0
        delta = k * mult * (score_h - exp_h)
        elo[h] += delta
        elo[a] -= delta
    return elo


def blended_rating(teams: pd.DataFrame, elo: dict, cfg: dict) -> pd.Series:
    """
    Rating z-normalizado que mezcla FIFA y Elo segun los pesos de settings.
    Es la base tanto del prior Dixon-Coles como de la interpretacion.
    """
    fifa = teams["fifa_points"].astype(float)
    fifa_z = (fifa - fifa.mean()) / fifa.std(ddof=0)
    elo_s = pd.Series({c: elo[c] for c in teams["code"]})
    elo_z = (elo_s - elo_s.mean()) / elo_s.std(ddof=0)
    w_f = cfg["ratings"]["w_fifa"]
    w_e = cfg["ratings"]["w_elo"]
    r = w_f * fifa_z + w_e * elo_z
    r.index = teams["code"]
    return r


def compute_ratings(teams: pd.DataFrame, matches: pd.DataFrame, cfg: dict,
                    as_of: pd.Timestamp):
    """Devuelve (elo_dict, rating_z_series)."""
    elo = update_elo(teams, matches, cfg, as_of)
    rating = blended_rating(teams, elo, cfg)
    return elo, rating
