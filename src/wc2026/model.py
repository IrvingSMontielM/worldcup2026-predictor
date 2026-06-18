"""
model.py
Modelo de goles Dixon-Coles regularizado.

Para cada equipo estima un parametro de ataque (atk) y de defensa (dfn).
Goles esperados del local:   mu = exp(intercept + atk[local] + dfn[visita] + ventaja)
Goles esperados del visita:  lam = exp(intercept + atk[visita] + dfn[local])

Particularidades:
  - Regularizacion ridge hacia un prior derivado del rating (FIFA+Elo). Con pocos
    partidos el modelo se apoya en el rating; con mas datos aprende el estilo real.
  - Decaimiento temporal: los partidos recientes pesan mas en la verosimilitud.
  - Correccion Dixon-Coles (rho) para los marcadores bajos (0-0,1-0,0-1,1-1).
La rejilla de marcadores permite calcular 1X2, over/under, BTTS y goles esperados
de forma analitica, sin simular.
"""
from __future__ import annotations
import json
import os
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

from . import ratings as R
from .io_load import ARTIFACTS


def _dc_tau(x, y, mu, lam, rho):
    """Factor de correccion Dixon-Coles para marcadores bajos."""
    if x == 0 and y == 0:
        return 1.0 - mu * lam * rho
    if x == 0 and y == 1:
        return 1.0 + mu * rho
    if x == 1 and y == 0:
        return 1.0 + lam * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def fit(teams: pd.DataFrame, matches: pd.DataFrame, cfg: dict, as_of) -> dict:
    """
    Ajusta el modelo y devuelve un dict de parametros serializable.
    Si no hay partidos, devuelve un modelo basado solo en el prior de rating.
    """
    elo, rating = R.compute_ratings(teams, matches, cfg, as_of)
    codes = list(teams["code"])
    idx = {c: i for i, c in enumerate(codes)}
    n = len(codes)

    mcfg = cfg["model"]
    atk_prior = (mcfg["atk_scale"] * rating.reindex(codes)).to_numpy()
    dfn_prior = (-mcfg["dfn_scale"] * rating.reindex(codes)).to_numpy()
    intercept0 = np.log(mcfg["base_total_goals"] / 2.0)

    # Sin datos: el modelo es el puro prior.
    if len(matches) == 0:
        params = dict(
            codes=codes, intercept=float(intercept0),
            home_adv=float(mcfg["home_adv_init"]), rho=float(mcfg["rho_init"]),
            atk={c: float(atk_prior[i]) for c, i in idx.items()},
            dfn={c: float(dfn_prior[i]) for c, i in idx.items()},
            elo={c: float(elo[c]) for c in codes},
            rating={c: float(rating[c]) for c in codes},
            n_matches=0,
        )
        return params

    # Vectores de datos
    hi = matches["home"].map(idx).to_numpy()
    ai = matches["away"].map(idx).to_numpy()
    hg = matches["home_goals"].to_numpy(dtype=int)
    ag = matches["away_goals"].to_numpy(dtype=int)
    adv = matches["home_adv"].to_numpy(dtype=float)
    w = R.temporal_weight(matches["date"], pd.Timestamp(as_of),
                          cfg["decay"]["half_life_days"])

    lam_ridge = mcfg["ridge_lambda"]

    # theta = [intercept, home_adv, rho, atk(n), dfn(n)]
    def unpack(theta):
        intercept = theta[0]
        home_adv = theta[1]
        rho = theta[2]
        atk = theta[3:3 + n]
        dfn = theta[3 + n:3 + 2 * n]
        return intercept, home_adv, rho, atk, dfn

    def neg_loglik(theta):
        intercept, home_adv, rho, atk, dfn = unpack(theta)
        log_mu = intercept + atk[hi] + dfn[ai] + home_adv * adv
        log_lam = intercept + atk[ai] + dfn[hi]
        mu = np.exp(np.clip(log_mu, -3, 3))
        lam = np.exp(np.clip(log_lam, -3, 3))
        # log Poisson sin la constante factorial (irrelevante para el optimo)
        ll = (-mu + hg * log_mu) + (-lam + ag * log_lam)
        # correccion DC solo donde aplica (marcadores 0/1)
        tau = np.ones_like(mu)
        mask = (hg <= 1) & (ag <= 1)
        for k in np.where(mask)[0]:
            tau[k] = max(_dc_tau(hg[k], ag[k], mu[k], lam[k], rho), 1e-6)
        ll = ll + np.log(tau)
        nll = -np.sum(w * ll)
        # ridge hacia el prior de rating
        nll += lam_ridge * (np.sum((atk - atk_prior) ** 2) +
                            np.sum((dfn - dfn_prior) ** 2))
        return nll

    theta0 = np.concatenate(([intercept0, mcfg["home_adv_init"], mcfg["rho_init"]],
                             atk_prior, dfn_prior))
    bounds = ([(np.log(0.4), np.log(4.0)), (0.0, 0.8), (-0.2, 0.2)] +
              [(-1.5, 1.5)] * n + [(-1.5, 1.5)] * n)

    res = minimize(neg_loglik, theta0, method="L-BFGS-B", bounds=bounds,
                   options={"maxiter": 500})
    intercept, home_adv, rho, atk, dfn = unpack(res.x)

    return dict(
        codes=codes, intercept=float(intercept), home_adv=float(home_adv),
        rho=float(rho),
        atk={c: float(atk[idx[c]]) for c in codes},
        dfn={c: float(dfn[idx[c]]) for c in codes},
        elo={c: float(elo[c]) for c in codes},
        rating={c: float(rating[c]) for c in codes},
        n_matches=int(len(matches)),
        converged=bool(res.success),
    )


def expected_goals(params: dict, home: str, away: str,
                   adv_home: float = 0.0, adv_away: float = 0.0):
    """Goles esperados base (sin contexto ni estilo) para local y visita."""
    ic = params["intercept"]
    ha = params["home_adv"]
    log_mu = ic + params["atk"][home] + params["dfn"][away] + ha * adv_home
    log_lam = ic + params["atk"][away] + params["dfn"][home] + ha * adv_away
    return float(np.exp(log_mu)), float(np.exp(log_lam))


def score_grid(mu: float, lam: float, rho: float, max_goals: int = 10) -> np.ndarray:
    """Matriz de probabilidad conjunta de marcadores con correccion Dixon-Coles."""
    gh = poisson.pmf(np.arange(max_goals + 1), mu)
    ga = poisson.pmf(np.arange(max_goals + 1), lam)
    grid = np.outer(gh, ga)
    # correccion en las cuatro celdas bajas
    grid[0, 0] *= 1.0 - mu * lam * rho
    grid[0, 1] *= 1.0 + mu * rho
    grid[1, 0] *= 1.0 + lam * rho
    grid[1, 1] *= 1.0 - rho
    grid = np.clip(grid, 0, None)
    grid /= grid.sum()
    return grid


def grid_markets(grid: np.ndarray) -> dict:
    """Probabilidades 1X2, over/under 2.5, BTTS y marcadores mas probables."""
    n = grid.shape[0]
    idx = np.arange(n)
    p_home = np.tril(grid, -1).sum()      # local mas goles
    p_draw = np.trace(grid)
    p_away = np.triu(grid, 1).sum()
    total = idx[:, None] + idx[None, :]
    p_over = grid[total >= 3].sum()
    p_over15 = grid[total >= 2].sum()
    p_over35 = grid[total >= 4].sum()
    p_btts = grid[1:, 1:].sum()
    # totales por equipo (probabilidad de marcar mas de 0.5 y 1.5 goles)
    p_home_o05 = grid[1:, :].sum()
    p_home_o15 = grid[2:, :].sum()
    p_away_o05 = grid[:, 1:].sum()
    p_away_o15 = grid[:, 2:].sum()
    # top marcadores
    flat = [((i, j), grid[i, j]) for i in range(n) for j in range(n)]
    flat.sort(key=lambda t: t[1], reverse=True)
    top = [{"score": f"{i}-{j}", "p": round(float(p), 4)} for (i, j), p in flat[:6]]
    exp_h = float((idx[:, None] * grid).sum())
    exp_a = float((idx[None, :] * grid).sum())
    return dict(p_home=float(p_home), p_draw=float(p_draw), p_away=float(p_away),
                p_over25=float(p_over), p_under25=float(1 - p_over),
                p_over15=float(p_over15), p_under15=float(1 - p_over15),
                p_over35=float(p_over35),
                p_home_over05=float(p_home_o05), p_home_over15=float(p_home_o15),
                p_away_over05=float(p_away_o05), p_away_over15=float(p_away_o15),
                p_btts=float(p_btts), top_scores=top,
                exp_goals_home=exp_h, exp_goals_away=exp_a)


def save_params(params: dict, path: str | None = None):
    path = path or os.path.join(ARTIFACTS, "params.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(params, f, ensure_ascii=False, indent=2)
    return path


def load_params(path: str | None = None) -> dict:
    path = path or os.path.join(ARTIFACTS, "params.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)
