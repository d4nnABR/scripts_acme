# ACME EV — Generador de telemetría

Generador de la flota ACME EV. Publica GPS (cada 30s) y Estado (cada 60s) a Confluent Cloud.

Dashboard en vivo: https://acme-ev-dashboard.vercel.app

## Setup (una sola vez)

```bash
git pull                       # traer la última versión del código
pip install -r requirements.txt
```

Crear un archivo `.env` copiando `.env.example` y pegar las credenciales de Confluent
que se comparten por el grupo. **Nunca subir el `.env` al repo.**

No se necesita Google Maps API key: `catalog.json` y `routes.json` ya vienen incluidos
con 300 vehículos pre-generados.

### ⚠️ Para correr 1k / 6k / 10k vehículos: copiar `routes_10000.json`

Las rutas reales de la flota grande viven en **`routes_10000.json`** (~176MB). Este
archivo **NO está en GitHub** (supera el límite de 100MB), así que `git pull` no lo
trae. Hay que **copiarlo aparte** (Drive / USB / WeTransfer) en esta carpeta.

Sin él, el generador **se detiene con un error** en lugar de inventar rutas
sintéticas feas (carros que cruzan el mar). Si ves ese error, pídele el archivo
a quien lo generó y cópialo aquí.

> Solo la opción de 300 vehículos funciona sin ese archivo (usa `routes.json`
> incluido en el repo).

## Correr el generador

```bash
python app.py
```

Al iniciar, el script pregunta dos cosas:

**1. Tamaño de flota:**
```
  [1]    300  vehículos  (demo — incluido en el repo)
  [2]  1,000  vehículos
  [3]  6,000  vehículos
  [4] 10,000  vehículos
```

**2. Tu número de operador** (para repartir la carga entre compañeros):
```
  [1]  Operador 1  (primer tercio)
  [2]  Operador 2  (segundo tercio)
  [3]  Operador 3  (tercer tercio)
  [0]  Toda la flota  (solo demo / pruebas locales)
```

> El repo incluye `catalog_10000.json` (10,000 clientes/vehículos reales). Cada
> opción del menú toma los **primeros N** de ese mismo archivo — elegir 6,000
> simula los primeros 6,000 vehículos. No se vuelve a llamar a ninguna API.
>
> Las rutas (`routes_10000.json`) son **rutas reales sobre calles** generadas con
> OSRM (OpenStreetMap), ~500 rutas únicas por sucursal. Ver "Generar rutas" abajo.

Detener con `Ctrl+C`. Mientras corre consume cuota de Confluent: apagarlo cuando
no se esté usando.

## Generar rutas (reales, sin API key)

Las rutas que recorren los vehículos se generan con **OSRM** (router público de
OpenStreetMap): rutas reales calle-por-calle, gratis, sin API key ni cuota. Un
filtro anti-mar descarta rutas que cruzan agua (evita "carros en el mar" en
ciudades costeras como Panamá).

```bash
# Regenerar las 10 sucursales a 500 rutas únicas c/u, rescatando las que ya
# estaban bien y completando con OSRM:
python regenerar_rutas_osrm.py --pool 500

# Solo una sucursal:
python regenerar_rutas_osrm.py SUC-009 --pool 500

# Generar desde cero una sucursal (sin rescatar nada):
python generar_rutas_sucursal.py SUC-008 --pool 500
```

`generar_rutas_reales.py` (Google Directions, requiere API key) queda como
alternativa, pero OSRM es el camino recomendado: sin cuotas ni `429`.

## Tests

```bash
python -m pytest tests/ -q
```
