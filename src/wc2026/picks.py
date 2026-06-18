"""
picks.py
Genera recomendaciones de apuesta para cada partido pendiente a partir del
modelo, con enfasis en mercados de baja varianza: doble oportunidad (1X, 12,
X2), over/under de goles (1.5 y 2.5), ambos anotan, y totales por equipo. Si
hay momios de mercado cargados (data/market_odds.csv para 1X2 o
data/market_totals.csv para over/under), calcula el valor (edge) del modelo
frente al mercado y marca los picks con ventaja.

Las probabilidades salen del grid Dixon-Coles, asi que esta capa es totalmente
automatica y no depende de ninguna fuente externa. El cruce con mercado es
opcional y solo enriquece la seleccion.

Importante: el modelo no conoce alineaciones, lesiones ni suspensiones de
ultima hora. Estas recomendaciones son cuantitativas; conviene revisar noticias
de plantel antes de cerrar cualquier apuesta.
"""
from __future__ import annotations
import pandas as pd


def _conf(p: float) -> str:
    """Etiqueta de confianza segun la probabilidad del modelo."""
    if p >= 0.80:
        return "Muy alta"
    if p >= 0.70:
        return "Alta"
    if p >= 0.62:
        return "Media"
    return "Baja"


def _devig_1x2(ph, pd_, pa):
    """Normaliza probabilidades implicitas 1X2 quitando el margen."""
    s = ph + pd_ + pa
    if s <= 0:
        return None
    return ph / s, pd_ / s, pa / s


def best_double_chance(ph, pd_, pa):
    """
    Elige la doble oportunidad mas fuerte excluyendo el resultado menos
    probable. Devuelve (codigo, etiqueta, probabilidad, resultado_excluido).
    """
    outcomes = {"1": ph, "X": pd_, "2": pa}
    excluded = min(outcomes, key=outcomes.get)
    if excluded == "2":
        return "1X", "Local o empate", ph + pd_, "2"
    if excluded == "1":
        return "X2", "Empate o visita", pd_ + pa, "1"
    return "12", "Local o visita", ph + pa, "X"


def _dc_market_prob(excluded, market_row):
    """Probabilidad de la doble oportunidad implicita en el mercado 1X2."""
    if market_row is None:
        return None
    fair = _devig_1x2(float(market_row["p_home"]), float(market_row["p_draw"]),
                      float(market_row["p_away"]))
    if fair is None:
        return None
    ph, pd_, pa = fair
    return {"2": ph + pd_, "1": pd_ + pa, "X": ph + pa}[excluded]


def match_picks(pred, teams, market_row=None, totals_row=None) -> dict:
    """
    Construye las recomendaciones de un partido. Devuelve un dict plano listo
    para tabla, con el pick principal (doble oportunidad), goles, ambos anotan,
    totales por equipo y lineas sugeridas de tiros, corners y tarjetas.
    """
    h, a = pred["home"], pred["away"]
    hn = teams.loc[h, "name_es"]
    an = teams.loc[a, "name_es"]
    p = pred["probs"]
    gm = pred["markets_goals"]
    mb = pred["markets_aux"]

    # doble oportunidad
    dc_code, dc_label, dc_prob, excl = best_double_chance(
        p["p_home"], p["p_draw"], p["p_away"])
    dc_market = _dc_market_prob(excl, market_row)
    dc_edge = (dc_prob - dc_market) if dc_market is not None else None

    # over/under 2.5 y 1.5
    ou25_label, ou25_p = (("Mas de 2.5", gm["p_over25"]) if gm["p_over25"] >= 0.5
                          else ("Menos de 2.5", gm["p_under25"]))
    ou15_label, ou15_p = (("Mas de 1.5", gm["p_over15"]) if gm["p_over15"] >= 0.5
                          else ("Menos de 1.5", gm["p_under15"]))
    ou25_market = float(totals_row["p_over25"]) if totals_row is not None else None
    if ou25_market is not None:
        ou25_edge = (gm["p_over25"] - ou25_market if ou25_label.startswith("Mas")
                     else (1 - ou25_market) - (1 - gm["p_over25"]))
    else:
        ou25_edge = None

    # ambos anotan
    btts_label, btts_p = (("Si", gm["p_btts"]) if gm["p_btts"] >= 0.5
                          else ("No", 1 - gm["p_btts"]))

    # lineas sugeridas (estadisticas, prior calibrable): una linea conservadora
    # se toma como el valor esperado redondeado hacia abajo a .5 menos un margen
    def _line(x, margin=1.0):
        return max(0.5, round((x - margin) * 2) / 2)

    pick = dict(
        match_no=pred.get("match_no"), date=pred.get("date"),
        group=pred.get("group"), home=h, away=a,
        partido=f"{hn} vs {an}", sede=pred["venue_name"],
        # pick principal
        pick_principal=f"{dc_code} ({dc_label})",
        pick_prob=round(dc_prob, 3), confianza=_conf(dc_prob),
        valor_vs_mercado=(None if dc_edge is None else round(dc_edge, 3)),
        # 1X2 crudo
        p_local=round(p["p_home"], 3), p_empate=round(p["p_draw"], 3),
        p_visita=round(p["p_away"], 3),
        # goles
        goles_esp=f"{gm['exp_goals_home']:.1f}-{gm['exp_goals_away']:.1f}",
        ou_25=f"{ou25_label} ({ou25_p*100:.0f}%)",
        ou_15=f"{ou15_label} ({ou15_p*100:.0f}%)",
        ou25_valor=(None if ou25_edge is None else round(ou25_edge, 3)),
        ambos_anotan=f"{btts_label} ({btts_p*100:.0f}%)",
        # totales por equipo
        local_anota=f"{gm['p_home_over05']*100:.0f}%",
        visita_anota=f"{gm['p_away_over05']*100:.0f}%",
        # lineas estadisticas sugeridas
        tiros=f"{hn} +{_line(mb['shots_home'])} / {an} +{_line(mb['shots_away'])}",
        tiros_puerta=f"{hn} +{_line(mb['shots_on_target_home'], 0.5)} / "
                     f"{an} +{_line(mb['shots_on_target_away'], 0.5)}",
        corners=f"{hn} +{_line(mb['corners_home'])} / {an} +{_line(mb['corners_away'])}",
        tarjetas_tot=f"+{_line(mb['cards_home'] + mb['cards_away'], 1.0)}",
    )
    # puntaje para ordenar: sin mercado favorece confianza alta pero no trivial
    # (un pick de 99% casi no paga); con mercado, el valor manda.
    sweet = dc_prob if dc_prob <= 0.82 else 0.82 - (dc_prob - 0.82) * 0.7
    bono = max(dc_edge, 0) if dc_edge is not None else 0.0
    pick["_score"] = sweet + 1.0 * bono
    pick["_rationale"] = _rationale(hn, an, p, gm, pred, dc_label, dc_prob,
                                    ou25_label, ou25_p, btts_label, btts_p, dc_edge)
    return pick


def _rationale(hn, an, p, gm, pred, dc_label, dc_prob, ou_label, ou_p,
               btts_label, btts_p, dc_edge):
    """Frase de justificacion basada en senales del modelo."""
    partes = [f"El modelo da {dc_prob*100:.0f}% a {dc_label.lower()}"]
    tot = gm["exp_goals_home"] + gm["exp_goals_away"]
    ritmo = "alto" if tot >= 2.8 else ("bajo" if tot < 2.2 else "moderado")
    partes.append(f"ritmo de goles {ritmo} (xG total {tot:.2f}), "
                  f"{ou_label.lower()} al {ou_p*100:.0f}%")
    if btts_p >= 0.58 or btts_p <= 0.42:
        partes.append(f"ambos anotan {btts_label.lower()} ({btts_p*100:.0f}%)")
    info = pred.get("context", {})
    if info.get("alt_factor_away", 1.0) <= 0.95 or info.get("alt_factor_home", 1.0) <= 0.95:
        partes.append(f"altitud relevante ({info.get('altitude_m','?')} m)")
    if dc_edge is not None and dc_edge >= 0.03:
        partes.append(f"con valor de {dc_edge*100:.0f} puntos sobre el mercado")
    return ". ".join(s[0].upper() + s[1:] for s in partes) + "."


def build_table(preds, teams, market_lookup=None, totals_lookup=None) -> pd.DataFrame:
    """
    Genera la tabla de picks para una lista de predicciones (una fila por
    partido), ordenada por puntaje descendente. market_lookup y totals_lookup
    son funciones (home, away) -> fila de mercado o None.
    """
    rows = []
    for pred in preds:
        mr = market_lookup(pred["home"], pred["away"]) if market_lookup else None
        tr = totals_lookup(pred["home"], pred["away"]) if totals_lookup else None
        rows.append(match_picks(pred, teams, mr, tr))
    df = pd.DataFrame(rows).sort_values("_score", ascending=False)
    return df.reset_index(drop=True)


def render_md(df: pd.DataFrame, generated_at: str) -> str:
    """Tablero de picks en markdown, con pick del dia y detalle por partido."""
    L = []
    L.append("# Picks de apuestas (generado por el modelo)\n")
    L.append(f"Ultima actualizacion: **{generated_at}**\n")
    L.append("Mercados de baja varianza priorizados: doble oportunidad, "
             "over/under y ambos anotan. Cuando hay momios cargados se calcula "
             "el valor frente al mercado.\n")

    if len(df):
        top = df.iloc[0]
        L.append("## Pick del dia\n")
        L.append(f"**{top['partido']}: {top['pick_principal']}** "
                 f"al {top['pick_prob']*100:.0f}% (confianza {top['confianza'].lower()}).  ")
        L.append(top["_rationale"] + "\n")

    L.append("## Tabla de picks\n")
    L.append("| Partido | Pick | Prob | Conf | Valor | O/U 2.5 | Ambos | Goles esp |")
    L.append("|---|---|---:|---|---:|---|---|:--:|")
    for _, r in df.iterrows():
        val = "" if r["valor_vs_mercado"] is None else f"{r['valor_vs_mercado']*100:+.0f}pp"
        L.append(f"| {r['partido']} | {r['pick_principal']} | "
                 f"{r['pick_prob']*100:.0f}% | {r['confianza']} | {val} | "
                 f"{r['ou_25']} | {r['ambos_anotan']} | {r['goles_esp']} |")

    L.append("\n## Detalle por partido\n")
    for _, r in df.iterrows():
        L.append(f"### {r['partido']}  ({r['date']}, Grupo {r['group']})")
        L.append(f"- Pick principal: **{r['pick_principal']}** "
                 f"({r['pick_prob']*100:.0f}%, {r['confianza'].lower()})")
        L.append(f"- 1X2: local {r['p_local']*100:.0f}% / empate "
                 f"{r['p_empate']*100:.0f}% / visita {r['p_visita']*100:.0f}%")
        L.append(f"- Goles: {r['ou_25']}, {r['ou_15']}, ambos anotan {r['ambos_anotan']}")
        L.append(f"- Tiros sugeridos: {r['tiros']}")
        L.append(f"- Tiros a puerta: {r['tiros_puerta']}")
        L.append(f"- Corners: {r['corners']}  |  Tarjetas totales: {r['tarjetas_tot']}")
        L.append(f"- Lectura: {r['_rationale']}\n")

    L.append("---\n")
    L.append("Recomendaciones cuantitativas del modelo. No incluyen noticias de "
             "alineacion, lesiones ni suspensiones; revisa el plantel y compara "
             "el momio en vivo (Polymarket, Betano, Caliente) antes de apostar.\n")
    return "\n".join(L)
