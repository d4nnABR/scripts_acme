# ACME EV — Generador de telemetría

Generador de la flota ACME EV: 300 vehículos repartidos entre 3 operadores.
Cada uno publica GPS (cada 30s) y Estado (cada 60s) a Confluent Cloud.

Dashboard en vivo: https://acme-ev-dashboard.vercel.app

## Setup (una sola vez)

```bash
pip install -r requirements.txt
```

Crear un archivo `.env` (copiar de `.env.example`) y pegar las credenciales
de Confluent que se comparten por el grupo. **Nunca subir el `.env` al repo.**

No se necesita Google Maps API key: `catalog.json` y `routes.json` ya vienen
incluidos con las rutas pre-generadas.

## Correr tu parte de la flota

Cada compañero corre **su número asignado** (1, 2 o 3):

```bash
python app.py 1   # operador 1 → 100 vehículos
python app.py 2   # operador 2 → 100 vehículos
python app.py 3   # operador 3 → 100 vehículos
```

Sin argumento (`python app.py`) corre los 300 — no usar salvo demo final.

Detener con `Ctrl+C`. Mientras corre consume cuota de Confluent:
apagarlo cuando no se esté usando.

## Tests

```bash
python -m pytest tests/ -q
```
