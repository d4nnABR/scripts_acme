"""Genera rutas REALES para UNA sola sucursal y las fusiona en routes_10000.json
— sin rutas sintéticas y SIN API key de Google.

Usa OSRM (router público de OpenStreetMap): rutas reales calle-por-calle,
gratis, sin cuota ni key. El mapa del dashboard sigue siendo Google Maps;
esto solo produce el archivo de rutas que los carros recorren.

Pensado para cuando una sucursal quedó con rutas pobres (p.ej. costera con
"carros en el mar"). INSISTE hasta obtener una ruta real válida (sobre calles)
por cada slot del pool, descartando rutas que cruzan agua.

Uso:
    python generar_rutas_sucursal.py SUC-008
    python generar_rutas_sucursal.py SUC-008 --pool 500
"""
import os
import json
import time
import argparse

from generator.routes import (
    _llamar_osrm, _punto_aleatorio_en_bbox, _ruta_sobre_calles,
)
from generator.catalog import cargar_catalogo

CATALOGO = "catalog_10000.json"
SALIDA   = "routes_10000.json"
POOL_DEFAULT = 500

# Ritmo entre llamadas a OSRM público: cortesía para no saturar el servidor
# demo. Si da error de red se sube solo y se relaja cuando vuelve a fluir.
SLEEP_BASE   = 0.4
SLEEP_MAX    = 6.0
MAX_INTENTOS_SLOT = 25   # tope de seguridad por ruta (evita bucle infinito)


def _parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("sucursal", help="id de sucursal, p.ej. SUC-008")
    p.add_argument("--pool", type=int, default=POOL_DEFAULT,
                   help=f"rutas reales a generar (default {POOL_DEFAULT})")
    return p.parse_args()


def main():
    args = _parse_args()
    catalogo = cargar_catalogo(CATALOGO)
    suc = next((s for s in catalogo["sucursales"] if s["id_sucursal"] == args.sucursal), None)
    if not suc:
        ids = ", ".join(s["id_sucursal"] for s in catalogo["sucursales"])
        raise SystemExit(f"Sucursal '{args.sucursal}' no existe. Disponibles: {ids}")

    bbox = suc["bbox"]
    veh = [v["id_vehiculo"] for v in catalogo["vehiculos"]
           if v["id_sucursal"] == args.sucursal]
    if not veh:
        raise SystemExit(f"{args.sucursal} no tiene vehículos en el catálogo")

    pool_n = min(args.pool, len(veh))
    print(f"{args.sucursal} ({suc.get('nombre_sucursal','')}): "
          f"generando {pool_n} rutas reales (OSRM, sin API key) "
          f"para {len(veh):,} vehículos\nbbox: {bbox}\n")

    pool = []
    sleep_actual = SLEEP_BASE
    llamadas = 0
    descartes_mar = 0

    while len(pool) < pool_n:
        # Insistir hasta conseguir UNA ruta real válida para este slot
        ruta = None
        for intento in range(MAX_INTENTOS_SLOT):
            origen  = _punto_aleatorio_en_bbox(bbox)
            destino = _punto_aleatorio_en_bbox(bbox)
            llamadas += 1
            try:
                cand = _llamar_osrm(origen, destino)
                sleep_actual = max(SLEEP_BASE, sleep_actual * 0.9)  # se relaja
            except Exception as e:
                sleep_actual = min(SLEEP_MAX, sleep_actual * 1.6)  # backoff red
                print(f"  error red ({e}) → ritmo {sleep_actual:.1f}s")
                time.sleep(sleep_actual)
                continue

            if _ruta_sobre_calles(cand):
                ruta = cand
                break
            descartes_mar += 1   # cruzó agua: descartar, otro punto
            time.sleep(sleep_actual)

        if ruta is None:
            # Tras MAX_INTENTOS_SLOT sin éxito: pausa larga y seguir (no sintética)
            print(f"  slot {len(pool)+1}: sin ruta tras {MAX_INTENTOS_SLOT} intentos, "
                  f"pausa 15s y reintenta")
            time.sleep(15)
            continue

        pool.append(ruta)
        if len(pool) % 50 == 0:
            print(f"  …{len(pool)}/{pool_n} rutas reales "
                  f"({llamadas:,} llamadas, {descartes_mar} descartes por agua)")
        time.sleep(sleep_actual)

    # Reusar el pool en bucle entre los vehículos de la sucursal
    rutas_existentes = {}
    if os.path.exists(SALIDA):
        with open(SALIDA, "r", encoding="utf-8") as f:
            rutas_existentes = json.load(f)
        print(f"\nFusionando con {SALIDA} ({len(rutas_existentes):,} rutas existentes)")

    for i, id_v in enumerate(veh):
        rutas_existentes[id_v] = pool[i % len(pool)]

    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(rutas_existentes, f)

    print(f"\nListo: {len(pool)} rutas reales (0 sintéticas) → "
          f"reusadas en {len(veh):,} vehículos de {args.sucursal}")
    print(f"Total llamadas a OSRM: {llamadas:,} | descartes por agua: {descartes_mar}")
    print(f"Guardado en {SALIDA}")


if __name__ == "__main__":
    main()
