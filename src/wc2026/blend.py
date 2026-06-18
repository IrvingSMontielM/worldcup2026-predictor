"""
blend.py
Mezcla la probabilidad 1X2 del modelo con la implicita del mercado
(Polymarket, Betano, casas de apuestas, Scout Picks, etc.).

No existe un API oficial gratuito y unificado de momios en vivo, asi que el flujo
es: pegas las probabilidades (o momios convertidos) en data/market_odds.csv y el
modelo las desvig-a (quita el margen) y las combina con un peso configurable.
Combinar modelo y mercado es practica estandar y suele mejorar la calibracion.
"""
from __future__ import annotations


def devig(p_home, p_draw, p_away):
    """Normaliza las probabilidades implicitas para quitar el margen (overround)."""
    s = p_home + p_draw + p_away
    if s <= 0:
        return None
    return p_home / s, p_draw / s, p_away / s


def odds_to_prob(o_home, o_draw, o_away):
    """Convierte momios decimales a probabilidades implicitas desvig-adas."""
    ph, pd_, pa = 1.0 / o_home, 1.0 / o_draw, 1.0 / o_away
    return devig(ph, pd_, pa)


def blend_1x2(model_probs, market_row, w_market):
    """
    model_probs: dict con p_home/p_draw/p_away del modelo.
    market_row: fila de market_odds.csv (o None).
    Devuelve (probs_finales, uso_mercado_bool).
    """
    if market_row is None or w_market <= 0:
        return model_probs, False
    mk = devig(float(market_row["p_home"]), float(market_row["p_draw"]),
               float(market_row["p_away"]))
    if mk is None:
        return model_probs, False
    w = w_market
    out = dict(
        p_home=(1 - w) * model_probs["p_home"] + w * mk[0],
        p_draw=(1 - w) * model_probs["p_draw"] + w * mk[1],
        p_away=(1 - w) * model_probs["p_away"] + w * mk[2],
    )
    s = out["p_home"] + out["p_draw"] + out["p_away"]
    for k in out:
        out[k] /= s
    return out, True
