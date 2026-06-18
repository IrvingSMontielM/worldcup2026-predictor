"""
build_data.py
Genera los archivos CSV base del proyecto a partir de la informacion oficial
de la Copa Mundial de la FIFA 2026 (grupos, sedes y calendario).

Ejecutar una sola vez (o cuando quieras regenerar los datos desde cero):
    python scripts/build_data.py

Los resultados ya disputados se siembran con marcador y status="played".
Los partidos pendientes quedan con status="scheduled" y sin marcador.
"""
from __future__ import annotations
import csv
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)

# ----------------------------------------------------------------------------
# 1) EQUIPOS
# Campos:
#   code, name_es, group, fifa_points (aproximado, EDITAR con valor oficial),
#   possession (0-1), set_piece (0-1 dependencia a balon parado),
#   cards_factor, corners_factor, shots_factor (multiplicadores de estilo, 1.0 = media)
# Los puntos FIFA son una semilla razonable; reemplazalos por los oficiales
# cuando los tengas. El modelo los usa solo como prior y se corrige con resultados.
# ----------------------------------------------------------------------------
TEAMS = [
    # code  name_es                 grp  fifa  poss  setp  card  corn  shot
    ("MEX", "Mexico",                "A", 1650, 0.52, 0.30, 1.10, 1.00, 1.00),
    ("RSA", "Sudafrica",             "A", 1440, 0.48, 0.32, 1.05, 0.95, 0.95),
    ("KOR", "Corea del Sur",         "A", 1585, 0.51, 0.30, 1.00, 1.00, 1.00),
    ("CZE", "Chequia",               "A", 1490, 0.50, 0.34, 1.05, 1.00, 0.98),
    ("CAN", "Canada",                "B", 1500, 0.50, 0.30, 1.05, 1.00, 1.00),
    ("BIH", "Bosnia y Herzegovina",  "B", 1430, 0.49, 0.33, 1.10, 1.00, 0.98),
    ("QAT", "Catar",                 "B", 1450, 0.52, 0.28, 1.00, 1.00, 0.97),
    ("SUI", "Suiza",                 "B", 1650, 0.52, 0.31, 1.00, 1.00, 1.00),
    ("BRA", "Brasil",                "C", 1780, 0.56, 0.26, 1.05, 1.10, 1.08),
    ("MAR", "Marruecos",             "C", 1710, 0.52, 0.31, 1.05, 1.00, 1.00),
    ("HAI", "Haiti",                 "C", 1320, 0.46, 0.30, 1.10, 0.92, 0.92),
    ("SCO", "Escocia",               "C", 1500, 0.49, 0.36, 1.10, 1.00, 0.97),
    ("USA", "Estados Unidos",        "D", 1660, 0.53, 0.30, 1.05, 1.02, 1.02),
    ("PAR", "Paraguay",              "D", 1480, 0.48, 0.33, 1.15, 0.97, 0.95),
    ("AUS", "Australia",             "D", 1530, 0.50, 0.34, 1.05, 1.00, 0.98),
    ("TUR", "Turquia",               "D", 1560, 0.53, 0.31, 1.10, 1.02, 1.02),
    ("GER", "Alemania",              "E", 1715, 0.58, 0.28, 0.92, 1.08, 1.08),
    ("CUW", "Curazao",               "E", 1310, 0.45, 0.30, 1.10, 0.90, 0.90),
    ("CIV", "Costa de Marfil",       "E", 1490, 0.51, 0.31, 1.05, 1.00, 1.00),
    ("ECU", "Ecuador",               "E", 1570, 0.50, 0.32, 1.10, 1.00, 0.98),
    ("NED", "Paises Bajos",          "F", 1750, 0.57, 0.28, 0.95, 1.06, 1.06),
    ("JPN", "Japon",                 "F", 1650, 0.55, 0.27, 0.88, 1.04, 1.04),
    ("SWE", "Suecia",                "F", 1560, 0.50, 0.34, 1.00, 1.00, 1.00),
    ("TUN", "Tunez",                 "F", 1500, 0.49, 0.31, 1.05, 0.97, 0.96),
    ("BEL", "Belgica",               "G", 1740, 0.55, 0.29, 1.00, 1.04, 1.05),
    ("EGY", "Egipto",                "G", 1510, 0.51, 0.31, 1.05, 1.00, 0.99),
    ("IRN", "Iran",                  "G", 1630, 0.50, 0.33, 1.05, 1.00, 0.98),
    ("NZL", "Nueva Zelanda",         "G", 1280, 0.47, 0.32, 1.05, 0.93, 0.92),
    ("ESP", "Espana",                "H", 1875, 0.62, 0.24, 0.95, 1.12, 1.10),
    ("CPV", "Cabo Verde",            "H", 1390, 0.48, 0.31, 1.05, 0.95, 0.94),
    ("KSA", "Arabia Saudi",          "H", 1420, 0.52, 0.29, 1.05, 0.98, 0.96),
    ("URU", "Uruguay",               "H", 1680, 0.51, 0.32, 1.15, 1.02, 1.01),
    ("FRA", "Francia",               "I", 1860, 0.55, 0.28, 1.00, 1.06, 1.07),
    ("SEN", "Senegal",               "I", 1640, 0.52, 0.31, 1.10, 1.00, 1.00),
    ("IRQ", "Irak",                  "I", 1380, 0.49, 0.31, 1.10, 0.95, 0.94),
    ("NOR", "Noruega",               "I", 1530, 0.51, 0.33, 1.00, 1.02, 1.03),
    ("ARG", "Argentina",             "J", 1885, 0.54, 0.30, 1.10, 1.04, 1.05),
    ("ALG", "Argelia",               "J", 1500, 0.52, 0.31, 1.10, 1.00, 0.99),
    ("AUT", "Austria",               "J", 1580, 0.52, 0.33, 1.05, 1.02, 1.01),
    ("JOR", "Jordania",              "J", 1380, 0.49, 0.30, 1.05, 0.95, 0.93),
    ("POR", "Portugal",              "K", 1770, 0.56, 0.29, 1.05, 1.06, 1.06),
    ("COD", "RD Congo",              "K", 1410, 0.50, 0.31, 1.10, 0.98, 0.97),
    ("UZB", "Uzbekistan",            "K", 1430, 0.50, 0.31, 1.05, 0.98, 0.96),
    ("COL", "Colombia",              "K", 1700, 0.53, 0.31, 1.10, 1.02, 1.01),
    ("ENG", "Inglaterra",            "L", 1820, 0.56, 0.30, 1.00, 1.06, 1.06),
    ("CRO", "Croacia",               "L", 1700, 0.55, 0.30, 1.05, 1.02, 1.00),
    ("GHA", "Ghana",                 "L", 1430, 0.50, 0.31, 1.10, 0.98, 0.97),
    ("PAN", "Panama",                "L", 1420, 0.49, 0.31, 1.10, 0.96, 0.94),
]

# Anfitriones: reciben ventaja de localia cuando juegan en su pais.
HOSTS = {"MEX", "USA", "CAN"}

# ----------------------------------------------------------------------------
# 2) SEDES
# Campos: code, name_es, country, lat, lon, altitude_m, capacity,
#         temp_c (norma junio/julio), humidity (0-1)
# ----------------------------------------------------------------------------
VENUES = [
    ("CDMX", "Estadio Ciudad de Mexico", "MEX", 19.303, -99.150, 2240, 83000, 19, 0.65),
    ("GDL",  "Estadio Guadalajara",      "MEX", 20.681, -103.462, 1566, 48000, 22, 0.55),
    ("MTY",  "Estadio Monterrey",        "MEX", 25.669, -100.244, 540, 53000, 28, 0.60),
    ("ATL",  "Estadio Atlanta",          "USA", 33.755, -84.401, 320, 71000, 27, 0.70),
    ("BOS",  "Estadio Boston",           "USA", 42.091, -71.264, 30, 65000, 22, 0.65),
    ("DAL",  "Estadio Dallas",           "USA", 32.747, -97.093, 180, 80000, 31, 0.60),
    ("HOU",  "Estadio Houston",          "USA", 29.685, -95.411, 15, 72000, 30, 0.75),
    ("KC",   "Estadio Kansas City",      "USA", 39.049, -94.484, 270, 76000, 28, 0.65),
    ("LA",   "Estadio Los Angeles",      "USA", 33.953, -118.339, 30, 70000, 22, 0.65),
    ("MIA",  "Estadio Miami",            "USA", 25.958, -80.239, 2, 65000, 31, 0.75),
    ("NYNJ", "Estadio Nueva York NJ",    "USA", 40.814, -74.074, 5, 82000, 26, 0.65),
    ("PHI",  "Estadio Filadelfia",       "USA", 39.901, -75.168, 12, 69000, 27, 0.68),
    ("SF",   "Estadio Bahia de San Francisco", "USA", 37.403, -121.969, 4, 68000, 22, 0.60),
    ("SEA",  "Estadio Seattle",          "USA", 47.595, -122.332, 5, 69000, 20, 0.60),
    ("TOR",  "Estadio Toronto",          "CAN", 43.633, -79.418, 80, 45000, 23, 0.65),
    ("VAN",  "Estadio BC Place Vancouver", "CAN", 49.277, -123.112, 5, 54000, 20, 0.70),
]

# ----------------------------------------------------------------------------
# 3) CALENDARIO DE FASE DE GRUPOS
# Tupla: (match_no, date, group, home, away, venue, home_goals, away_goals, status)
# status: "played" o "scheduled". Para "scheduled" los goles van como "".
# Marcadores tomados del calendario oficial (Documento de entrada).
# ----------------------------------------------------------------------------
GS = [
    # Jornada 1 (jugada salvo el ultimo)
    (1,  "2026-06-11", "A", "MEX", "RSA", "CDMX", 2, 0, "played"),
    (2,  "2026-06-11", "A", "KOR", "CZE", "GDL",  2, 1, "played"),
    (3,  "2026-06-12", "B", "CAN", "BIH", "TOR",  1, 1, "played"),
    (4,  "2026-06-12", "D", "USA", "PAR", "LA",   4, 1, "played"),
    (5,  "2026-06-13", "B", "QAT", "SUI", "SF",   1, 1, "played"),
    (6,  "2026-06-13", "C", "BRA", "MAR", "NYNJ", 1, 1, "played"),
    (7,  "2026-06-13", "C", "HAI", "SCO", "BOS",  0, 1, "played"),
    (8,  "2026-06-13", "D", "AUS", "TUR", "VAN",  2, 0, "played"),
    (9,  "2026-06-14", "E", "GER", "CUW", "HOU",  7, 1, "played"),
    (10, "2026-06-14", "F", "NED", "JPN", "DAL",  2, 2, "played"),
    (11, "2026-06-14", "E", "CIV", "ECU", "PHI",  1, 0, "played"),
    (12, "2026-06-14", "F", "SWE", "TUN", "MTY",  5, 1, "played"),
    (13, "2026-06-15", "H", "ESP", "CPV", "ATL",  0, 0, "played"),
    (14, "2026-06-15", "G", "BEL", "EGY", "SEA",  1, 1, "played"),
    (15, "2026-06-15", "H", "KSA", "URU", "MIA",  1, 1, "played"),
    (16, "2026-06-15", "G", "IRN", "NZL", "LA",   2, 2, "played"),
    (17, "2026-06-16", "I", "FRA", "SEN", "NYNJ", 3, 1, "played"),
    (18, "2026-06-16", "I", "IRQ", "NOR", "BOS",  1, 4, "played"),
    (19, "2026-06-16", "J", "ARG", "ALG", "KC",   3, 0, "played"),
    (20, "2026-06-16", "J", "AUT", "JOR", "SF",   3, 1, "played"),
    (21, "2026-06-17", "K", "POR", "COD", "HOU",  0, 0, "played"),
    (22, "2026-06-17", "L", "ENG", "CRO", "DAL",  4, 2, "played"),
    (23, "2026-06-17", "L", "GHA", "PAN", "TOR",  1, 0, "played"),
    (24, "2026-06-17", "K", "UZB", "COL", "CDMX", "", "", "scheduled"),
    # Jornada 2
    (25, "2026-06-18", "A", "CZE", "RSA", "ATL",  "", "", "scheduled"),
    (26, "2026-06-18", "B", "SUI", "BIH", "LA",   "", "", "scheduled"),
    (27, "2026-06-18", "B", "CAN", "QAT", "VAN",  "", "", "scheduled"),
    (28, "2026-06-18", "A", "MEX", "KOR", "GDL",  "", "", "scheduled"),
    (29, "2026-06-19", "D", "USA", "AUS", "SEA",  "", "", "scheduled"),
    (30, "2026-06-19", "C", "SCO", "MAR", "BOS",  "", "", "scheduled"),
    (31, "2026-06-19", "C", "BRA", "HAI", "PHI",  "", "", "scheduled"),
    (32, "2026-06-19", "D", "TUR", "PAR", "SF",   "", "", "scheduled"),
    (33, "2026-06-20", "F", "NED", "SWE", "HOU",  "", "", "scheduled"),
    (34, "2026-06-20", "E", "GER", "CIV", "TOR",  "", "", "scheduled"),
    (35, "2026-06-20", "E", "ECU", "CUW", "KC",   "", "", "scheduled"),
    (36, "2026-06-20", "F", "TUN", "JPN", "MTY",  "", "", "scheduled"),
    (37, "2026-06-21", "H", "ESP", "KSA", "ATL",  "", "", "scheduled"),
    (38, "2026-06-21", "G", "BEL", "IRN", "LA",   "", "", "scheduled"),
    (39, "2026-06-21", "H", "URU", "CPV", "MIA",  "", "", "scheduled"),
    (40, "2026-06-21", "G", "NZL", "EGY", "VAN",  "", "", "scheduled"),
    (41, "2026-06-22", "J", "ARG", "AUT", "DAL",  "", "", "scheduled"),
    (42, "2026-06-22", "I", "FRA", "IRQ", "PHI",  "", "", "scheduled"),
    (43, "2026-06-22", "I", "NOR", "SEN", "NYNJ", "", "", "scheduled"),
    (44, "2026-06-22", "J", "JOR", "ALG", "SF",   "", "", "scheduled"),
    (45, "2026-06-23", "K", "POR", "UZB", "HOU",  "", "", "scheduled"),
    (46, "2026-06-23", "L", "ENG", "GHA", "BOS",  "", "", "scheduled"),
    (47, "2026-06-23", "L", "PAN", "CRO", "TOR",  "", "", "scheduled"),
    (48, "2026-06-23", "K", "COL", "COD", "GDL",  "", "", "scheduled"),
    # Jornada 3
    (49, "2026-06-24", "B", "SUI", "CAN", "VAN",  "", "", "scheduled"),
    (50, "2026-06-24", "B", "BIH", "QAT", "SEA",  "", "", "scheduled"),
    (51, "2026-06-24", "C", "SCO", "BRA", "MIA",  "", "", "scheduled"),
    (52, "2026-06-24", "C", "MAR", "HAI", "ATL",  "", "", "scheduled"),
    (53, "2026-06-24", "A", "CZE", "MEX", "CDMX", "", "", "scheduled"),
    (54, "2026-06-24", "A", "RSA", "KOR", "MTY",  "", "", "scheduled"),
    (55, "2026-06-25", "E", "CUW", "CIV", "PHI",  "", "", "scheduled"),
    (56, "2026-06-25", "E", "ECU", "GER", "NYNJ", "", "", "scheduled"),
    (57, "2026-06-25", "F", "JPN", "SWE", "DAL",  "", "", "scheduled"),
    (58, "2026-06-25", "F", "TUN", "NED", "KC",   "", "", "scheduled"),
    (59, "2026-06-25", "D", "TUR", "USA", "LA",   "", "", "scheduled"),
    (60, "2026-06-25", "D", "PAR", "AUS", "SF",   "", "", "scheduled"),
    (61, "2026-06-26", "I", "NOR", "FRA", "BOS",  "", "", "scheduled"),
    (62, "2026-06-26", "I", "SEN", "IRQ", "TOR",  "", "", "scheduled"),
    (63, "2026-06-26", "H", "CPV", "KSA", "HOU",  "", "", "scheduled"),
    (64, "2026-06-26", "H", "URU", "ESP", "GDL",  "", "", "scheduled"),
    (65, "2026-06-26", "G", "EGY", "IRN", "SEA",  "", "", "scheduled"),
    (66, "2026-06-26", "G", "NZL", "BEL", "VAN",  "", "", "scheduled"),
    (67, "2026-06-27", "L", "PAN", "ENG", "NYNJ", "", "", "scheduled"),
    (68, "2026-06-27", "L", "CRO", "GHA", "PHI",  "", "", "scheduled"),
    (69, "2026-06-27", "K", "COL", "POR", "MIA",  "", "", "scheduled"),
    (70, "2026-06-27", "K", "COD", "UZB", "ATL",  "", "", "scheduled"),
    (71, "2026-06-27", "J", "ALG", "AUT", "KC",   "", "", "scheduled"),
    (72, "2026-06-27", "J", "JOR", "ARG", "DAL",  "", "", "scheduled"),
]


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  escrito {os.path.relpath(path, ROOT)} ({len(rows)} filas)")


def main():
    print("Generando datos base...")

    # teams.csv
    rows = []
    for c, n, g, p, poss, sp, cf, cof, sf in TEAMS:
        host = 1 if c in HOSTS else 0
        rows.append([c, n, g, p, host, poss, sp, cf, cof, sf])
    write_csv(
        os.path.join(DATA, "teams.csv"),
        ["code", "name_es", "group", "fifa_points", "host",
         "possession", "set_piece", "cards_factor", "corners_factor", "shots_factor"],
        rows,
    )

    # venues.csv
    write_csv(
        os.path.join(DATA, "venues.csv"),
        ["code", "name_es", "country", "lat", "lon", "altitude_m", "capacity", "temp_c", "humidity"],
        [list(v) for v in VENUES],
    )

    # fixtures_group.csv
    write_csv(
        os.path.join(DATA, "fixtures_group.csv"),
        ["match_no", "date", "group", "home", "away", "venue", "home_goals", "away_goals", "status"],
        [list(m) for m in GS],
    )

    # players.csv (plantilla: una fila de jugador clave por equipo, nombre en blanco)
    # star_rating se deriva de los puntos FIFA (0-1). form=1.0, injury="" (none/doubtful/out).
    pmin = min(t[3] for t in TEAMS)
    pmax = max(t[3] for t in TEAMS)
    prows = []
    for c, n, g, p, *_ in TEAMS:
        star = round(0.45 + 0.5 * (p - pmin) / (pmax - pmin), 3)
        prows.append([c, "", "FW", star, 1.0, ""])
    write_csv(
        os.path.join(DATA, "players.csv"),
        ["team", "player_name", "role", "star_rating", "form", "injury"],
        prows,
    )

    # market_odds.csv (plantilla vacia para pegar momios/probabilidades de mercado)
    write_csv(
        os.path.join(DATA, "market_odds.csv"),
        ["match_no", "home", "away", "p_home", "p_draw", "p_away", "source"],
        [],
    )

    # matches_history.csv (plantilla para que agregues internacionales de los ultimos 4 anios)
    write_csv(
        os.path.join(DATA, "matches_history.csv"),
        ["date", "home", "away", "home_goals", "away_goals", "home_adv", "competition"],
        [],
    )

    print("Listo. Datos en data/.")


if __name__ == "__main__":
    main()
