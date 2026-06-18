# worldcup2026-predictor

Modelo de predicción para la Copa Mundial de la FIFA 2026 (48 selecciones, sedes en México, Estados Unidos y Canadá). Predice resultados de partido (1X2, marcadores, over/under, ambos marcan), tiros de esquina, tiros, tiros a puerta y tarjetas por equipo, y simula el torneo completo miles de veces para estimar la probabilidad de que cada selección avance, gane su grupo y llegue a cada ronda hasta el título. Es dinámico: conforme registras los resultados reales del Mundial, solo se simulan los partidos pendientes y el pronóstico se afina.

El motor combina un modelo de goles Dixon-Coles regularizado con un rating mixto (ranking FIFA más un Elo dinámico), ajustes de contexto (altitud, calor, humedad, densidad del aire, desgaste por viaje, localía y aforo), un factor de individualidad del jugador y, de forma opcional, una mezcla con el mercado de apuestas. Todo corre sin servicios externos: clonas, instalas cuatro dependencias y ejecutas.

## Qué es y qué no es (lee esto una vez)

Conviene ser claro con cuatro puntos para que el alcance quede bien entendido.

No existe un API oficial, gratuito y en vivo de la FIFA: el portal oficial renderiza con JavaScript y no expone un feed abierto estable. Por eso el flujo de datos en vivo es manual y rápido: registras cada resultado con `scripts/update.py` y el modelo se recalcula. Esto es deliberado, no una limitación de pereza: una actualización por CSV es más confiable que raspar una página que cambia de estructura. El código deja un punto de enganche claro por si más adelante conectas una fuente que tú controles.

"Betalpha" es una plataforma de análisis cuantitativo financiero, no un modelo de fútbol; su filosofía (combinar señales y regularizar) sí está reflejada aquí. "David Clement y su modelo" corresponde al estilo de analítica de goles esperados con base Poisson; el enfoque Dixon-Coles que implementa este repositorio es exactamente esa familia de modelos.

Los datos de mercado (Polymarket, Betano, Scout Picks, casas de apuestas) no tienen un API unificado gratuito. El modelo los ingiere por CSV: pegas las probabilidades implícitas en `data/market_odds.csv`, el código les quita el margen (de-vig) y las mezcla con el modelo. Combinar modelo y mercado es práctica estándar y suele mejorar la calibración.

Los nombres de jugadores en `data/players.csv` van en blanco a propósito. La individualidad se modela de forma abstracta con `star_rating`, `form` e `injury`, sin atribuir actuaciones concretas a atletas reales por nombre. Si quieres, llenas tú los nombres y ajustas esos tres campos.

## Instalación y uso rápido

```bash
git clone https://github.com/IrvingSMontielM/worldcup2026-predictor.git
cd worldcup2026-predictor
pip install -r requirements.txt

python scripts/build_data.py        # genera los CSV base (una sola vez)
python scripts/fit.py               # ajusta el modelo con los partidos jugados
python scripts/predict.py BRA HAI PHI   # predice un partido (local visita sede)
python scripts/run_tournament.py    # simula el torneo completo
```

Eso es todo. `build_data.py` escribe los datos oficiales (grupos, sedes, calendario y los resultados ya disputados) en `data/`. `fit.py` ajusta el modelo de goles y guarda los parámetros en `artifacts/params.json`. A partir de ahí, `predict.py` y `run_tournament.py` ya funcionan.

Los códigos de equipo y de sede están en `data/teams.csv` y `data/venues.csv`. Ejemplos de predicción de partido:

```bash
python scripts/predict.py MEX KOR GDL --n 50000   # mas simulaciones, mas estable
python scripts/predict.py ESP URU GDL
python scripts/run_tournament.py --n 50000 --seed 7 --groups A,H --save artifacts/torneo.csv
```

## Cómo se vuelve dinámico

Cada vez que termina un partido de la fase de grupos, registras el marcador y vuelves a calcular:

```bash
python scripts/update.py --list             # ve los partidos pendientes y su numero
python scripts/update.py 24 2 1             # el partido 24 termino 2-1
python scripts/fit.py                       # reajusta el modelo con el nuevo dato
python scripts/run_tournament.py            # nuevo pronostico
```

Como el simulador fija los partidos jugados y solo simula los pendientes, las probabilidades se vuelven más nítidas a medida que avanza el torneo. El Elo y el prior del modelo también incorporan cada resultado nuevo.

## Qué hace el modelo por dentro

El corazón es un modelo Dixon-Coles. Para cada selección estima un parámetro de ataque y uno de defensa, y los goles esperados de un partido salen de `exp(intercepto + ataque_local + defensa_visita + ventaja_local)` para el local, y simétrico para la visita. La corrección Dixon-Coles ajusta la probabilidad de los marcadores bajos (0-0, 1-0, 0-1, 1-1), que un Poisson puro modela mal.

Con pocos partidos jugados (al inicio del Mundial hay alrededor de dos decenas) un ajuste libre sería ruidoso, así que el modelo se regulariza (ridge) hacia un prior derivado del rating de cada equipo. El rating mezcla el puntaje FIFA normalizado con un Elo que parte de ese mismo puntaje y se actualiza con cada resultado, ponderando el margen de victoria y la localía. En la práctica: al principio el modelo se apoya en el rating, y conforme entran resultados aprende el estilo real de cada selección. No hay doble conteo: el rating solo alimenta el prior; los parámetros de ataque y defensa son los que predicen.

Un decaimiento temporal exponencial da más peso a los partidos recientes que a los viejos, con vida media configurable (un año por defecto).

Sobre esos goles esperados se aplican multiplicadores de contexto acotados: penalización por altitud para selecciones no aclimatadas (México y Ecuador quedan exentos; la Ciudad de México a 2240 m es la sede de mayor efecto), reducción de ritmo por calor y humedad, desgaste por distancia de viaje, y ventaja de localía para los anfitriones cuando juegan en su país, escalada por el aforo esperado. La densidad del aire se calcula con la fórmula barométrica y la de Tetens para el vapor de agua.

Los tiros de esquina, tiros y tarjetas se derivan de la fuerza ofensiva relativa (a partir de los goles esperados) y del estilo de cada equipo (posesión, dependencia al balón parado, propensión a tarjetas). Las tarjetas suben en partidos parejos. Estas tasas son priors razonables y se calibran con datos reales (ver más abajo).

La individualidad del jugador entra como un "momento de figura": con cierta probabilidad, ligada al `star_rating` del equipo, aparece un gol extra inesperado que puede romper el resultado esperado. El reporte de partido indica en qué porcentaje de las simulaciones ese momento cambió el marcador.

Finalmente, cada predicción es analítica y simulada a la vez. La rejilla de marcadores da el 1X2, el over/under, el ambos-marcan y los goles esperados de forma exacta; las simulaciones Monte Carlo construyen la narrativa de "qué esperar". Para el torneo se corren miles de simulaciones completas: se arman las tablas de los 12 grupos, se eligen los 8 mejores terceros, se asignan a los cruces de dieciseisavos y se resuelve el cuadro hasta la final.

## Archivos de datos

Todos los datos viven en `data/` como CSV editables.

`teams.csv` tiene las 48 selecciones con su grupo, puntos FIFA (un valor inicial razonable, editable), si es anfitrión, y factores de estilo (posesión, balón parado, tarjetas, corners, tiros). `venues.csv` tiene las 16 sedes con coordenadas, altitud, capacidad, temperatura y humedad típicas. `fixtures_group.csv` tiene los 72 partidos de grupos: los disputados con marcador y `status` igual a "played", los pendientes con `status` igual a "scheduled". `bracket.yaml` describe toda la fase de eliminación con la notación de cruces oficial.

`players.csv` lleva una fila por selección (la figura), con nombres en blanco y campos `star_rating`, `form` e `injury` que tú ajustas. `market_odds.csv` empieza vacío: agrega filas con `match_no`, equipos y probabilidades `p_home`, `p_draw`, `p_away` cuando quieras mezclar con el mercado. `matches_history.csv` también empieza vacío: si agregas internacionales de los últimos años (con `date`, equipos, goles, `home_adv` y `competition`), el modelo los usa con su decaimiento temporal y el ajuste mejora.

## Configuración y calibración

Todos los parámetros del modelo están en `config/settings.yaml` y se cambian sin tocar el código: pesos del rating, factor K del Elo, vida media del decaimiento, fuerza del prior, multiplicadores de contexto, número de simulaciones, tasas base de los mercados, peso del mercado y los parámetros de individualidad.

Los puntos FIFA de `teams.csv` son una semilla; reemplázalos por los oficiales cuando los tengas para un mejor prior. Las tasas base de corners, tiros y tarjetas en `settings.yaml` son priors; si tienes promedios reales por selección, ajústalos ahí o cambia los factores de estilo por equipo en `teams.csv`. El peso del mercado (`w_market`, 0.35 por defecto) controla cuánto pesa el mercado frente al modelo en el 1X2 final; ponlo en 0 para usar solo el modelo.

## Supuestos y limitaciones

El desempate de grupos usa puntos, diferencia de goles y goles a favor. El desempate por enfrentamiento directo que aplica la FIFA no está implementado, así que en grupos muy apretados el orden puede diferir del oficial. La asignación de los 8 mejores terceros a los cruces de dieciseisavos resuelve un emparejamiento válido respetando los grupos permitidos de cada cruce; es una aproximación de la tabla oficial de la FIFA y encuentra una asignación consistente, no necesariamente la tabulada. Los empates en eliminación se resuelven con una moneda ponderada por los goles esperados, como proxy de prórroga y penales.

Los factores de estilo, las tasas de mercado y los parámetros de individualidad son priors calibrables, no verdades medidas. El modelo es tan bueno como sus datos: con más historial en `matches_history.csv` y puntos FIFA oficiales en `teams.csv`, las predicciones mejoran. Las estimaciones de probabilidad tienen ruido de Monte Carlo que baja al subir el número de simulaciones (`--n`).

## Estructura del repositorio

```
worldcup2026-predictor/
├── config/
│   └── settings.yaml          # parametros del modelo (editables)
├── data/
│   ├── teams.csv              # 48 selecciones, grupo, puntos FIFA, estilo
│   ├── venues.csv             # 16 sedes, altitud, clima, capacidad
│   ├── fixtures_group.csv     # 72 partidos de grupos (jugados + pendientes)
│   ├── bracket.yaml           # estructura de la fase de eliminacion
│   ├── players.csv            # figura por seleccion (nombres en blanco)
│   ├── market_odds.csv        # momios de mercado (opcional)
│   └── matches_history.csv    # historico de internacionales (opcional)
├── src/wc2026/
│   ├── io_load.py             # carga de datos y configuracion
│   ├── ratings.py             # rating FIFA + Elo dinamico + decaimiento
│   ├── model.py               # Dixon-Coles regularizado (ajuste y rejilla)
│   ├── context.py             # altitud, calor, viaje, localia, densidad del aire
│   ├── markets.py             # corners, tiros, tarjetas
│   ├── blend.py               # mezcla con el mercado
│   ├── simulate.py            # motor de partido (analitico + Monte Carlo)
│   ├── tournament.py          # simulacion del torneo completo
│   └── report.py              # reportes en espanol
├── scripts/
│   ├── build_data.py          # genera los CSV base
│   ├── fit.py                 # ajusta el modelo
│   ├── predict.py             # predice un partido
│   ├── run_tournament.py      # simula el torneo
│   └── update.py              # registra resultados reales
├── artifacts/                 # parametros y salidas generadas
├── requirements.txt
├── LICENSE
└── README.md
```

## Licencia

MIT. Ver `LICENSE`.
