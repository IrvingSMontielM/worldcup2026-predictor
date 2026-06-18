"""
markets.py
Mercados auxiliares: tiros de esquina, tiros (totales y a puerta) y tarjetas.

Las tasas base se escalan con la fuerza ofensiva relativa de cada equipo
(derivada de los goles esperados) y con su estilo (posesion, dependencia a
balon parado, propension a tarjetas). Las tarjetas suben en partidos parejos.

Estos parametros son priors razonables. Calibralos con datos reales de
tiros/corners/tarjetas si los tienes (ver README, seccion de calibracion).
"""
from __future__ import annotations
import numpy as np


def _attack_scale(mu_team: float, base_total: float) -> float:
    """Fuerza ofensiva relativa: cuanto mas goles esperados, mas tiros y corners."""
    ref = base_total / 2.0
    return float(np.clip(mu_team / max(ref, 1e-6), 0.55, 1.8))


def expected_corners(team_row, opp_row, mu_team, cfg):
    base = cfg["markets"]["base_corners"]
    scale = _attack_scale(mu_team, cfg["model"]["base_total_goals"])
    # mas posesion propia y menos del rival -> mas corners
    poss = 0.85 + 0.6 * (team_row["possession"] - opp_row["possession"] + 0.5)
    return base * scale * team_row["corners_factor"] * np.clip(poss, 0.7, 1.4)


def expected_shots(team_row, mu_team, cfg):
    base = cfg["markets"]["base_shots"]
    scale = _attack_scale(mu_team, cfg["model"]["base_total_goals"])
    return base * scale * team_row["shots_factor"]


def expected_cards(home_row, away_row, p_draw, cfg):
    """
    Reparte las tarjetas esperadas del partido entre ambos equipos.
    La tension (probabilidad de empate alta = partido cerrado) las incrementa.
    """
    m = cfg["markets"]
    tension = 1.0 + m["tension_card_boost"] * (p_draw - 0.25)
    total = m["base_cards_match"] * max(tension, 0.7)
    w_home = home_row["cards_factor"]
    w_away = away_row["cards_factor"]
    s = w_home + w_away
    return total * w_home / s, total * w_away / s


def sample_market(rng, lam):
    """Una realizacion Poisson de una tasa esperada."""
    return int(rng.poisson(max(lam, 0.01)))


def market_block(params, teams, cfg, home, away, mu_h, mu_a, p_draw):
    """Valores esperados (no aleatorios) de los mercados para el reporte."""
    hr, ar = teams.loc[home], teams.loc[away]
    ch = expected_corners(hr, ar, mu_h, cfg)
    ca = expected_corners(ar, hr, mu_a, cfg)
    sh = expected_shots(hr, mu_h, cfg)
    sa = expected_shots(ar, mu_a, cfg)
    sot = cfg["markets"]["shots_on_target_ratio"]
    kh, ka = expected_cards(hr, ar, p_draw, cfg)
    return dict(
        corners_home=round(float(ch), 1), corners_away=round(float(ca), 1),
        shots_home=round(float(sh), 1), shots_away=round(float(sa), 1),
        shots_on_target_home=round(float(sh * sot), 1),
        shots_on_target_away=round(float(sa * sot), 1),
        cards_home=round(float(kh), 1), cards_away=round(float(ka), 1),
        red_card_prob=cfg["markets"]["red_card_prob"],
    )
