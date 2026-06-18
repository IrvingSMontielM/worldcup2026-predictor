"""
context.py
Ajustes contextuales sobre los goles esperados. Cada funcion devuelve un
multiplicador acotado para el equipo correspondiente.

Cubre: altitud, calor/humedad, densidad del aire, desgaste por viaje,
ventaja de localia del anfitrion y efecto de asistencia.
"""
from __future__ import annotations
import math

R_DRY = 287.058   # constante del aire seco J/(kg*K)
R_VAP = 461.495   # constante del vapor de agua


def air_density(temp_c: float, altitude_m: float, humidity: float) -> float:
    """
    Densidad del aire (kg/m3) por altitud, temperatura y humedad relativa.
    Aire menos denso (altura/calor) -> el balon vuela mas y hay mas desgaste.
    """
    t_k = temp_c + 273.15
    # presion barometrica aproximada por altitud
    p = 101325.0 * (1.0 - 2.25577e-5 * altitude_m) ** 5.25588
    # presion de vapor de saturacion (Tetens) y presion de vapor real
    p_sat = 610.78 * 10 ** (7.5 * temp_c / (temp_c + 237.3))
    p_v = humidity * p_sat
    p_d = p - p_v
    return p_d / (R_DRY * t_k) + p_v / (R_VAP * t_k)


def altitude_factor(team_code: str, venue_row, cfg: dict) -> float:
    """Penalizacion por altitud para seleccionados no habituados."""
    c = cfg["context"]
    if team_code in c["altitude_home_nations"]:
        return 1.0
    over_km = max(venue_row["altitude_m"] - c["altitude_ref_m"], 0) / 1000.0
    return max(1.0 - c["altitude_penalty_per_km"] * over_km, 0.80)


def heat_factor(venue_row, cfg: dict) -> float:
    """Reduccion de ritmo por estres de calor y humedad (afecta a ambos)."""
    c = cfg["context"]
    # indice simple: temperatura ajustada por humedad
    feels = venue_row["temp_c"] + 6.0 * (venue_row["humidity"] - 0.5)
    over = max(feels - c["heat_wbgt_threshold"], 0.0)
    return max(1.0 - c["heat_penalty_per_deg"] * over, 0.88)


def travel_factor(distance_km: float, cfg: dict) -> float:
    """Penalizacion por viaje desde el partido previo."""
    c = cfg["context"]
    pen = c["travel_penalty_per_1000km"] * (distance_km / 1000.0)
    return max(1.0 - min(pen, c["travel_cap"]), 0.90)


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Distancia en km entre dos sedes."""
    rad = math.pi / 180.0
    dlat = (lat2 - lat1) * rad
    dlon = (lon2 - lon1) * rad
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(lat1 * rad) * math.cos(lat2 * rad) * math.sin(dlon / 2) ** 2)
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def home_advantage(team_code, venue_row, teams, cfg, attendance=None) -> float:
    """
    Ventaja de localia del anfitrion (en escala log, se suma a la ventaja base).
    Solo aplica si el equipo es anfitrion y juega en su pais. Escala con la
    asistencia local esperada.
    """
    if teams.loc[team_code, "host"] != 1:
        return 0.0
    host_country = {"MEX": "MEX", "USA": "USA", "CAN": "CAN"}.get(team_code, "")
    if host_country != venue_row["country"]:
        return 0.0
    att = cfg["context"]["attendance_default"] if attendance is None else attendance
    return 1.0 + cfg["context"]["crowd_home_weight"] * (att * 100.0 - 90.0)


def context_multipliers(home, away, venue_row, teams, cfg,
                        travel_home_km=0.0, travel_away_km=0.0, attendance=None):
    """
    Devuelve (mult_home, mult_away, adv_home, adv_away, info) donde adv_* es el
    flag/peso de ventaja de localia que multiplica el parametro home_adv del modelo.
    """
    heat = heat_factor(venue_row, cfg)  # afecta a ambos por igual
    mh = altitude_factor(home, venue_row, cfg) * heat * travel_factor(travel_home_km, cfg)
    ma = altitude_factor(away, venue_row, cfg) * heat * travel_factor(travel_away_km, cfg)

    adv_home = home_advantage(home, venue_row, teams, cfg, attendance)
    adv_away = home_advantage(away, venue_row, teams, cfg, attendance)

    info = dict(
        air_density=round(air_density(venue_row["temp_c"], venue_row["altitude_m"],
                                      venue_row["humidity"]), 3),
        altitude_m=int(venue_row["altitude_m"]),
        temp_c=float(venue_row["temp_c"]),
        humidity=float(venue_row["humidity"]),
        heat_factor=round(heat, 3),
        alt_factor_home=round(altitude_factor(home, venue_row, cfg), 3),
        alt_factor_away=round(altitude_factor(away, venue_row, cfg), 3),
    )
    return mh, ma, adv_home, adv_away, info
