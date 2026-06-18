"""
odds.py
Ingesta opcional de momios de mercado desde The Odds API (the-odds-api.com),
que cubre el Mundial con sport_key=soccer_fifa_world_cup y agrega decenas de
casas. Escribe el consenso de mercado en data/market_odds.csv (1X2) y
data/market_totals.csv (over/under 2.5), que picks.py usa para calcular valor.

Requiere la variable de entorno ODDS_API_KEY (capa gratuita ~500 peticiones al
mes). Sin key, sync.py simplemente omite esta capa y los picks salen del modelo.

Nota sobre Polymarket, Betano y Caliente: no exponen un API libre unificado.
The Odds API entrega el consenso de muchas casas, que es un proxy solido del
mercado. Si quieres especificamente Polymarket y Kalshi, OddsPapi (oddspapi.io)
los incluye en su capa gratuita y este modulo se puede adaptar a esa fuente.
"""
from __future__ import annotations
import os
import urllib.parse

from . import live as LV


_BASE = "https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds"


def _devig(implied: dict) -> dict:
    s = sum(implied.values())
    return {k: v / s for k, v in implied.items()} if s > 0 else implied


def _event_1x2(ev, home_name, away_name):
    """Consenso 1X2 (de-vig promediado entre casas) de un evento."""
    accum = {"home": [], "draw": [], "away": []}
    for bk in ev.get("bookmakers", []):
        for mk in bk.get("markets", []):
            if mk.get("key") != "h2h":
                continue
            imp, ok = {}, True
            for o in mk.get("outcomes", []):
                price = o.get("price", 0) or 0
                if price <= 1:
                    ok = False
                    break
                name = o.get("name", "")
                if name == "Draw":
                    imp["draw"] = 1.0 / price
                elif name == home_name:
                    imp["home"] = 1.0 / price
                elif name == away_name:
                    imp["away"] = 1.0 / price
            if ok and len(imp) == 3:
                fair = _devig(imp)
                for k in accum:
                    accum[k].append(fair[k])
    if not accum["home"]:
        return None
    return {k: sum(v) / len(v) for k, v in accum.items()}


def _event_total25(ev):
    """Consenso de over 2.5 (de-vig promediado) de un evento."""
    overs = []
    for bk in ev.get("bookmakers", []):
        for mk in bk.get("markets", []):
            if mk.get("key") != "totals":
                continue
            po = pu = None
            for o in mk.get("outcomes", []):
                if abs(float(o.get("point", 0)) - 2.5) > 1e-6:
                    continue
                price = o.get("price", 0) or 0
                if price <= 1:
                    continue
                if o.get("name") == "Over":
                    po = 1.0 / price
                elif o.get("name") == "Under":
                    pu = 1.0 / price
            if po and pu:
                overs.append(po / (po + pu))
    return sum(overs) / len(overs) if overs else None


def fetch_and_write(teams, fixtures, regions: str = "eu") -> dict:
    """
    Descarga momios, los mapea a codigos y match_no, y escribe los CSV de
    mercado. Devuelve conteos {odds_1x2, totals}. Lanza si falta la key.
    """
    api_key = os.environ.get("ODDS_API_KEY", "")
    if not api_key:
        raise RuntimeError("Falta ODDS_API_KEY para la ingesta de momios.")

    qs = urllib.parse.urlencode({
        "regions": regions, "markets": "h2h,totals",
        "oddsFormat": "decimal", "apiKey": api_key})
    events = LV._http_get_json(f"{_BASE}?{qs}")
    if not isinstance(events, list):
        raise RuntimeError(f"Respuesta inesperada de The Odds API: {str(events)[:200]}")

    crosswalk = LV.build_crosswalk(teams)
    valid = set(teams["code"])

    # indice de partidos por par de codigos -> match_no
    pair_to_match = {}
    for _, r in fixtures.iterrows():
        pair_to_match[frozenset((r["home"], r["away"]))] = (
            int(r["match_no"]), r["home"], r["away"])

    rows_1x2, rows_tot = [], []
    for ev in events:
        hn, an = ev.get("home_team"), ev.get("away_team")
        hc = LV.resolve_code(hn, crosswalk, valid)
        ac = LV.resolve_code(an, crosswalk, valid)
        if hc is None or ac is None:
            continue
        key = frozenset((hc, ac))
        if key not in pair_to_match:
            continue
        match_no, fx_home, fx_away = pair_to_match[key]

        p = _event_1x2(ev, hn, an)
        if p is not None:
            # orientar al calendario: si la API invierte local y visita
            ph, pa = (p["home"], p["away"]) if hc == fx_home else (p["away"], p["home"])
            rows_1x2.append((match_no, fx_home, fx_away, round(ph, 4),
                             round(p["draw"], 4), round(pa, 4), "the-odds-api"))

        po = _event_total25(ev)
        if po is not None:
            rows_tot.append((match_no, fx_home, fx_away, round(po, 4), "the-odds-api"))

    _write_csv(os.path.join(LV_DATA(), "market_odds.csv"),
               "match_no,home,away,p_home,p_draw,p_away,source", rows_1x2)
    _write_csv(os.path.join(LV_DATA(), "market_totals.csv"),
               "match_no,home,away,p_over25,source", rows_tot)
    return {"odds_1x2": len(rows_1x2), "totals": len(rows_tot)}


def LV_DATA():
    from . import io_load as IO
    return IO.DATA


def _write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n")
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\n")
