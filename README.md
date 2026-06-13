# ACME EV — Generador de telemetría

Generador de la flota ACME EV. Publica GPS (cada 30s) y Estado (cada 60s) a Confluent Cloud.

Dashboard en vivo: https://acme-ev-dashboard.vercel.app

## Setup (una sola vez)

```bash
pip install -r requirements.txt
```

Crear un archivo `.env` copiando `.env.example` y pegar las credenciales de Confluent
que se comparten por el grupo. **Nunca subir el `.env` al repo.**

No se necesita Google Maps API key: `catalog.json` y `routes.json` ya vienen incluidos
con 300 vehículos pre-generados.

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
> Las rutas para 1k/6k/10k se generan sintéticas la primera vez (sin Google Maps)
> y quedan cacheadas en `routes_<N>.json`.

Detener con `Ctrl+C`. Mientras corre consume cuota de Confluent: apagarlo cuando
no se esté usando.

## Tests

```bash
python -m pytest tests/ -q
```
