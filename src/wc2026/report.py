"""
report.py
Formatea en espanol los resultados del modelo: reporte de partido (1X2,
marcadores, mercados, contexto y una sugerencia en lenguaje natural) y reporte
de torneo (probabilidades de avance, ganar grupo y llegar a cada ronda).
"""
from __future__ import annotations
import pandas as pd


def _pct(x):
    return f"{100.0 * x:.1f}%"


def _narrativa(pred, teams):
    """Sugerencia en lenguaje natural de lo que puede pasar en el partido."""
    h = teams.loc[pred["home"], "name_es"]
    a = teams.loc[pred["away"], "name_es"]
    p = pred["probs"]
    sim = pred["sim"]
    gm = pred["markets_goals"]

    fav, pfav = (h, p["p_home"]) if p["p_home"] >= p["p_away"] else (a, p["p_away"])
    if abs(p["p_home"] - p["p_away"]) < 0.08:
        encabezado = f"Partido parejo. {h} y {a} llegan muy igualados"
    elif pfav > 0.55:
        encabezado = f"{fav} es claro favorito"
    else:
        encabezado = f"Ligera ventaja para {fav}"

    top = gm["top_scores"][0]
    ritmo = "alto" if gm["exp_goals_home"] + gm["exp_goals_away"] >= 2.8 else "moderado"
    if gm["exp_goals_home"] + gm["exp_goals_away"] < 2.2:
        ritmo = "bajo"

    partes = [
        f"{encabezado} (victoria {h} {_pct(p['p_home'])}, empate "
        f"{_pct(p['p_draw'])}, victoria {a} {_pct(p['p_away'])}).",
        f"Se anticipa un ritmo de goles {ritmo}: el marcador mas probable es "
        f"{top['score']} y la linea de 2.5 goles cae del lado "
        f"{'over' if gm['p_over25'] >= 0.5 else 'under'} "
        f"({_pct(gm['p_over25'])} over).",
    ]
    if sim["star_decided_pct"] >= 12:
        partes.append(
            f"Hay margen para que una individualidad rompa el guion: en "
            f"{sim['star_decided_pct']}% de las simulaciones un momento de figura "
            f"cambio el resultado.")
    if gm["p_btts"] >= 0.55:
        partes.append("Probable que ambos equipos marquen.")
    info = pred["context"]
    if info.get("alt_factor_away", 1.0) <= 0.95 or info.get("alt_factor_home", 1.0) <= 0.95:
        partes.append(
            f"La altitud de la sede ({info['altitude_m']} m) penaliza al equipo "
            f"no aclimatado.")
    if info.get("heat_factor", 1.0) <= 0.96:
        partes.append(
            f"El calor y la humedad ({info['temp_c']:.0f} C, "
            f"{100 * info['humidity']:.0f}%) bajan el ritmo.")
    return " ".join(partes)


def match_report(pred, teams) -> str:
    """Reporte de texto de un partido."""
    h = teams.loc[pred["home"], "name_es"]
    a = teams.loc[pred["away"], "name_es"]
    p = pred["probs"]
    gm = pred["markets_goals"]
    mb = pred["markets_aux"]
    info = pred["context"]
    L = []
    L.append(f"PREDICCION  {h}  vs  {a}")
    L.append(f"Sede: {pred['venue_name']}  |  simulaciones: {pred['n_sim']:,}")
    if pred["used_market"]:
        L.append("(1X2 mezclado con mercado)")
    L.append("")
    L.append("Resultado (1X2)")
    L.append(f"  Gana {h}: {_pct(p['p_home'])}")
    L.append(f"  Empate:  {_pct(p['p_draw'])}")
    L.append(f"  Gana {a}: {_pct(p['p_away'])}")
    L.append("")
    L.append("Goles")
    L.append(f"  Esperados: {h} {gm['exp_goals_home']:.2f}  -  "
             f"{gm['exp_goals_away']:.2f} {a}")
    L.append(f"  Over 2.5: {_pct(gm['p_over25'])}   Under 2.5: {_pct(gm['p_under25'])}")
    L.append(f"  Ambos marcan: {_pct(gm['p_btts'])}")
    L.append("  Marcadores mas probables: " +
             ", ".join(f"{s['score']} ({_pct(s['p'])})" for s in gm["top_scores"][:4]))
    L.append("")
    L.append("Mercados por equipo (valores esperados)")
    L.append(f"  Tiros de esquina:  {h} {mb['corners_home']}  |  {a} {mb['corners_away']}")
    L.append(f"  Tiros:             {h} {mb['shots_home']}  |  {a} {mb['shots_away']}")
    L.append(f"  Tiros a puerta:    {h} {mb['shots_on_target_home']}  |  "
             f"{a} {mb['shots_on_target_away']}")
    L.append(f"  Tarjetas:          {h} {mb['cards_home']}  |  {a} {mb['cards_away']}")
    L.append(f"  Prob. roja en el partido: {_pct(mb['red_card_prob'])}")
    L.append("")
    L.append("Contexto")
    L.append(f"  Altitud {info['altitude_m']} m  |  temp {info['temp_c']:.0f} C  |  "
             f"humedad {100 * info['humidity']:.0f}%  |  "
             f"densidad aire {info['air_density']} kg/m3")
    L.append("")
    L.append("Que esperar")
    L.append("  " + _narrativa(pred, teams))
    return "\n".join(L)


def tournament_report(df: pd.DataFrame, top: int = 16) -> str:
    """Reporte de texto del torneo (probabilidades principales)."""
    L = []
    L.append("PRONOSTICO DEL TORNEO")
    L.append(f"Selecciones ordenadas por probabilidad de campeon (top {top})")
    L.append("")
    head = (f"{'Seleccion':<22}{'Gpo':<4}{'Avanza':>8}{'1oGpo':>8}"
            f"{'8vos':>8}{'4tos':>8}{'Semis':>8}{'Final':>8}{'Campeon':>9}")
    L.append(head)
    L.append("-" * len(head))
    for c, r in df.head(top).iterrows():
        L.append(f"{r['name']:<22}{r['group']:<4}"
                 f"{_pct(r['p_advance']):>8}{_pct(r['p_win_group']):>8}"
                 f"{_pct(r['p_R16']):>8}{_pct(r['p_QF']):>8}"
                 f"{_pct(r['p_SF']):>8}{_pct(r['p_final']):>8}"
                 f"{_pct(r['p_champion']):>9}")
    return "\n".join(L)


def group_projection(df: pd.DataFrame, group: str) -> str:
    """Proyeccion de posiciones finales de un grupo."""
    sub = df[df["group"] == group].sort_values("p_win_group", ascending=False)
    L = [f"GRUPO {group}  (proyeccion de posicion final)"]
    L.append(f"{'Seleccion':<22}{'1o':>7}{'2o':>7}{'3o':>7}{'4o':>7}{'Avanza':>9}")
    for c, r in sub.iterrows():
        L.append(f"{r['name']:<22}{_pct(r['p_g1']):>7}{_pct(r['p_g2']):>7}"
                 f"{_pct(r['p_g3']):>7}{_pct(r['p_g4']):>7}{_pct(r['p_advance']):>9}")
    return "\n".join(L)
