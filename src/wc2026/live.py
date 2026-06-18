"""
live.py
Ingesta de resultados en vivo. Consulta una API de futbol, detecta los partidos
ya finalizados y los traduce al esquema de fixtures_group.csv (match_no, goles,
status), sin tocar el resto del pipeline.

Proveedores soportados:
  - "apifootball" : API-Football (api-sports.io). Cubre el Mundial con
                    league=1 y season=2026. Requiere una API key gratuita en la
                    variable de entorno API_FOOTBALL_KEY. Recomendado.
  - "opensource"  : worldcup26.ir, REST gratuito sin autenticacion. Mejor
                    esfuerzo: el esquema es de un tercero y puede cambiar.
  - "none"        : no consulta nada (el pipeline corre con lo que ya hay).

Diseno deliberado: este modulo solo escribe resultados finales en el CSV. La
dinamica del modelo es por partido cerrado, no minuto a minuto.
"""
from __future__ import annotations
import json
import os
import unicodedata
import urllib.request
import urllib.parse

import pandas as pd


# ---------------------------------------------------------------------------
# Crosswalk de nombres a codigos
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    """Normaliza un nombre: minusculas, sin acentos, solo alfanumerico y espacios."""
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = "".join(c if c.isalnum() else " " for c in s)
    return " ".join(s.split())


# Alias en ingles y variantes frecuentes de las APIs hacia el codigo FIFA local.
# El nombre en espanol de teams.csv y el propio codigo se agregan en tiempo real.
_ALIASES = {
    "mexico": "MEX",
    "south africa": "RSA",
    "korea republic": "KOR", "south korea": "KOR", "republic of korea": "KOR",
    "czechia": "CZE", "czech republic": "CZE",
    "canada": "CAN",
    "bosnia and herzegovina": "BIH", "bosnia herzegovina": "BIH",
    "qatar": "QAT",
    "switzerland": "SUI",
    "brazil": "BRA",
    "morocco": "MAR",
    "haiti": "HAI",
    "scotland": "SCO",
    "usa": "USA", "united states": "USA", "united states of america": "USA",
    "paraguay": "PAR",
    "australia": "AUS",
    "turkey": "TUR", "turkiye": "TUR",
    "germany": "GER",
    "curacao": "CUW",
    "cote d ivoire": "CIV", "ivory coast": "CIV",
    "ecuador": "ECU",
    "netherlands": "NED", "holland": "NED",
    "japan": "JPN",
    "sweden": "SWE",
    "tunisia": "TUN",
    "belgium": "BEL",
    "egypt": "EGY",
    "iran": "IRN", "ir iran": "IRN", "iran islamic republic": "IRN",
    "new zealand": "NZL",
    "spain": "ESP",
    "cape verde": "CPV", "cape verde islands": "CPV",
    "saudi arabia": "KSA",
    "uruguay": "URU",
    "france": "FRA",
    "senegal": "SEN",
    "iraq": "IRQ",
    "norway": "NOR",
    "argentina": "ARG",
    "algeria": "ALG",
    "austria": "AUT",
    "jordan": "JOR",
    "portugal": "POR",
    "dr congo": "COD", "congo dr": "COD",
    "democratic republic of the congo": "COD", "democratic republic of congo": "COD",
    "congo democratic republic": "COD", "congo": "COD",
    "uzbekistan": "UZB",
    "colombia": "COL",
    "england": "ENG",
    "croatia": "CRO",
    "ghana": "GHA",
    "panama": "PAN",
}


def build_crosswalk(teams: pd.DataFrame) -> dict:
    """
    Construye el mapa nombre/codigo -> codigo a partir de los alias en ingles,
    el nombre en espanol de teams.csv y el propio codigo FIFA. Devuelve un dict
    con claves normalizadas.
    """
    cw = dict(_ALIASES)
    for code in teams["code"]:
        cw[_norm(code)] = code
        cw[_norm(teams.loc[code, "name_es"])] = code
    return {_norm(k): v for k, v in cw.items()}


def resolve_code(value, crosswalk: dict, valid_codes: set) -> str | None:
    """
    Resuelve un nombre o codigo de la API a un codigo local. Devuelve None si no
    hay coincidencia (el llamador decide que hacer con los no resueltos).
    """
    if value is None:
        return None
    raw = str(value).strip().upper()
    if raw in valid_codes:
        return raw
    return crosswalk.get(_norm(value))


# ---------------------------------------------------------------------------
# Utilidad HTTP (sin dependencias extra; usa la biblioteca estandar)
# ---------------------------------------------------------------------------

def _http_get_json(url: str, headers: dict | None = None, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Proveedores: devuelven lista normalizada de partidos finalizados
#   [{date, home, away, home_goals, away_goals}]
# ---------------------------------------------------------------------------

_FINISHED = {"FT", "AET", "PEN", "PEN_LIVE", "AWD", "WO"}


def fetch_apifootball(crosswalk, valid_codes, api_key: str,
                      season: int = 2026, league: int = 1) -> list:
    """
    Resultados finalizados desde API-Football (api-sports.io).
    Endpoint: /fixtures?league=1&season=2026. Header x-apisports-key.
    """
    if not api_key:
        raise RuntimeError("Falta API_FOOTBALL_KEY para el proveedor apifootball.")
    base = "https://v3.football.api-sports.io/fixtures"
    qs = urllib.parse.urlencode({"league": league, "season": season})
    data = _http_get_json(f"{base}?{qs}", headers={"x-apisports-key": api_key})

    errors = data.get("errors")
    if errors:
        raise RuntimeError(f"API-Football devolvio errores: {errors}")

    out, unresolved = [], []
    for item in data.get("response", []):
        status = (item.get("fixture", {}).get("status", {}) or {}).get("short", "")
        if status not in _FINISHED:
            continue
        goals = item.get("goals", {}) or {}
        gh, ga = goals.get("home"), goals.get("away")
        if gh is None or ga is None:
            continue
        teams_obj = item.get("teams", {}) or {}
        hn = (teams_obj.get("home", {}) or {}).get("name")
        an = (teams_obj.get("away", {}) or {}).get("name")
        hc = resolve_code(hn, crosswalk, valid_codes)
        ac = resolve_code(an, crosswalk, valid_codes)
        if hc is None or ac is None:
            unresolved.append((hn, an))
            continue
        date = (item.get("fixture", {}).get("date", "") or "")[:10]
        out.append(dict(date=date, home=hc, away=ac,
                        home_goals=int(gh), away_goals=int(ga)))
    if unresolved:
        print(f"  Aviso: {len(unresolved)} equipos no resueltos en el crosswalk: "
              f"{unresolved[:5]}")
    return out


def fetch_opensource(crosswalk, valid_codes) -> list:
    """
    Mejor esfuerzo contra worldcup26.ir (/get/games), gratuito y sin auth. El
    esquema es de un tercero; si no se puede interpretar, devuelve lista vacia.
    """
    data = _http_get_json("https://worldcup26.ir/get/games")
    games = data if isinstance(data, list) else (
        data.get("games") or data.get("data") or data.get("matches") or [])

    def pick(d, keys):
        for k in keys:
            if k in d and d[k] not in (None, ""):
                return d[k]
        return None

    out = []
    for g in games:
        if not isinstance(g, dict):
            continue
        gh = pick(g, ["home_score", "score_home", "home_goals", "goals_home"])
        ga = pick(g, ["away_score", "score_away", "away_goals", "goals_away"])
        if gh is None or ga is None:
            continue
        try:
            gh, ga = int(gh), int(ga)
        except (TypeError, ValueError):
            continue
        hv = pick(g, ["home", "home_team", "team_home", "home_code",
                      "home_fifa", "homeName"])
        av = pick(g, ["away", "away_team", "team_away", "away_code",
                      "away_fifa", "awayName"])
        if isinstance(hv, dict):
            hv = pick(hv, ["fifa_code", "code", "name_en", "name"])
        if isinstance(av, dict):
            av = pick(av, ["fifa_code", "code", "name_en", "name"])
        hc = resolve_code(hv, crosswalk, valid_codes)
        ac = resolve_code(av, crosswalk, valid_codes)
        if hc is None or ac is None:
            continue
        date = str(pick(g, ["date", "utc_date", "datetime", "kickoff"]) or "")[:10]
        out.append(dict(date=date, home=hc, away=ac,
                        home_goals=gh, away_goals=ga))
    return out


def fetch_results(provider: str, crosswalk, valid_codes,
                  api_key: str = "", season: int = 2026) -> list:
    """Despacha al proveedor elegido."""
    provider = (provider or "none").lower()
    if provider == "apifootball":
        return fetch_apifootball(crosswalk, valid_codes, api_key, season)
    if provider == "opensource":
        return fetch_opensource(crosswalk, valid_codes)
    if provider == "none":
        return []
    raise ValueError(f"Proveedor desconocido: {provider}")


# ---------------------------------------------------------------------------
# Escritura idempotente en fixtures_group.csv
# ---------------------------------------------------------------------------

def apply_results(results: list, fixtures_path: str) -> list:
    """
    Escribe los resultados finalizados en fixtures_group.csv. Solo actualiza
    filas cuyo marcador cambie (idempotente: no genera commits si nada cambio).
    Empareja por (local, visita) y, si la API invierte el orden, por el par sin
    orden respetando la orientacion del calendario. Devuelve la lista aplicada
    [(match_no, home, away, gh, ga)].
    """
    if not results:
        return []
    df = pd.read_csv(fixtures_path)
    applied = []

    for r in results:
        hc, ac, gh, ga = r["home"], r["away"], r["home_goals"], r["away_goals"]
        mask = (df["home"] == hc) & (df["away"] == ac)
        swapped = False
        if not mask.any():
            mask = (df["home"] == ac) & (df["away"] == hc)
            swapped = True
        if not mask.any():
            continue  # no es un partido de fase de grupos (o equipos no calzan)

        i = df.index[mask][0]
        new_h, new_a = (ga, gh) if swapped else (gh, ga)
        cur_h, cur_a = df.at[i, "home_goals"], df.at[i, "away_goals"]
        already = (str(df.at[i, "status"]) == "played"
                   and pd.notna(cur_h) and pd.notna(cur_a)
                   and int(cur_h) == int(new_h) and int(cur_a) == int(new_a))
        if already:
            continue

        df.at[i, "home_goals"] = int(new_h)
        df.at[i, "away_goals"] = int(new_a)
        df.at[i, "status"] = "played"
        applied.append((int(df.at[i, "match_no"]), df.at[i, "home"],
                        df.at[i, "away"], int(new_h), int(new_a)))

    if applied:
        df.to_csv(fixtures_path, index=False)
    return applied
