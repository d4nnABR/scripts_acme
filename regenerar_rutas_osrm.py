"""Regenera SELECTIVAMENTE el pool de rutas de las 10 sucursales con OSRM,
rescatando las rutas reales de Google que ya están bien.

Por cada sucursal:
  1. Extrae las rutas únicas del pool actual (las rutas se reúsan entre vehículos).
  2. Clasifica cada una:
       - RESCATAR: real que sigue calles (salto máx <= UMBRAL_RESCATE m).
       - REGENERAR: sintética, o cruza agua de verdad (salto > UMBRAL_RESCATE).
  3. Reemplaza solo las REGENERAR por rutas reales nuevas de OSRM (anti-mar
     estricto: salto <= UMBRAL_BUENA). Mantiene el tamaño del pool.
  4. Reasigna el pool resultante a los vehículos de la sucursal.

OSRM es gratis y sin key. El mapa del dashboard sigue siendo Google Maps.

Cada sucursal queda con un pool de POOL_OBJETIVO rutas reales (rescatadas +
nuevas de OSRM), para dar variedad real (no 30 rutas reusadas en 1000 carros).

Uso:
    python regenerar_rutas_osrm.py            # las 10 sucursales
    python regenerar_rutas_osrm.py SUC-002    # solo una
    python regenerar_rutas_osrm.py --pool 200 # tamaño de pool por sucursal
"""
import sys
import json
import math
import time

from generator.routes import _llamar_osrm, _punto_aleatorio_en_bbox
from generator.catalog import cargar_catalogo

CATALOGO = "catalog_10000.json"
SALIDA   = "routes_10000.json"

# Rutas únicas por sucursal: variedad alta (antes había solo ~30 reusadas).
POOL_OBJETIVO = 500

# Una ruta REAL de Google con saltos hasta 1500 m puede ser una avenida/autopista
# larga sin waypoints intermedios → se rescata. Por encima ya es cruce de agua.
UMBRAL_RESCATE = 1500
# Las rutas NUEVAS de OSRM se exigen más limpias (no avenidas raras).
UMBRAL_BUENA   = 700
SLEEP_BASE = 0.4
SLEEP_MAX  = 6.0
MAX_INTENTOS_SLOT = 25


def _hav(a, b):
    R = 6_371_000
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp = math.radians(b["lat"] - a["lat"]); dl = math.radians(b["lng"] - a["lng"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))

def _salto_max(r):
    return max((_hav(r[i], r[i + 1]) for i in range(len(r) - 1)), default=9e9)

def _es_sintetica(r):
    if len(r) < 3:
        return True
    ds = [_hav(r[i], r[i + 1]) for i in range(min(20, len(r) - 1))]
    return 38 < sum(ds) / len(ds) < 46   # paso ~40 m constante

def _rescatable(r):
    """True si es una ruta real que vale la pena conservar."""
    return len(r) >= 3 and not _es_sintetica(r) and _salto_max(r) <= UMBRAL_RESCATE

def _ruta_osrm_buena(bbox, sleep):
    """Pide a OSRM hasta lograr una ruta real limpia (anti-mar estricto)."""
    for _ in range(MAX_INTENTOS_SLOT):
        o = _punto_aleatorio_en_bbox(bbox)
        d = _punto_aleatorio_en_bbox(bbox)
        try:
            cand = _llamar_osrm(o, d)
        except Exception as e:
            print(f"    red ({e})"); time.sleep(min(SLEEP_MAX, sleep * 1.6)); continue
        if len(cand) >= 3 and _salto_max(cand) <= UMBRAL_BUENA:
            return cand
        time.sleep(sleep)
    return None


def main():
    args = [a for a in sys.argv[1:]]
    pool_obj = POOL_OBJETIVO
    if "--pool" in args:
        i = args.index("--pool"); pool_obj = int(args[i + 1]); del args[i:i + 2]
    objetivo = args[0] if args else None

    catalogo = cargar_catalogo(CATALOGO)
    rutas = json.load(open(SALIDA, encoding="utf-8")) if __import__("os").path.exists(SALIDA) else {}

    por_suc = {}
    for v in catalogo["vehiculos"]:
        por_suc.setdefault(v["id_sucursal"], []).append(v["id_vehiculo"])
    suc_map = {s["id_sucursal"]: s for s in catalogo["sucursales"]}

    sucursales = [objetivo] if objetivo else list(por_suc.keys())
    total_osrm = 0

    for sid in sucursales:
        suc = suc_map.get(sid)
        veh = por_suc.get(sid, [])
        if not suc or not veh:
            print(f"{sid}: sin datos, salto"); continue
        bbox = suc["bbox"]
        objetivo_suc = min(pool_obj, len(veh))

        # Pool único actual de la sucursal (rutas distintas que se reúsan)
        pool, vistos = [], set()
        for vid in veh:
            r = rutas.get(vid)
            if not r:
                continue
            p0 = r[0]
            firma = (round(p0["lat"], 5), round(p0["lng"], 5), len(r))
            if firma not in vistos:
                vistos.add(firma); pool.append(r)

        # Rescatar las reales buenas (hasta el objetivo) y completar con OSRM
        rescatadas = [r for r in pool if _rescatable(r)][:objetivo_suc]
        n_generar = objetivo_suc - len(rescatadas)
        print(f"\n{sid} ({suc.get('nombre_sucursal','')}): objetivo {objetivo_suc} "
              f"→ rescato {len(rescatadas)}, genero {n_generar} con OSRM")

        nuevas = []
        sleep = SLEEP_BASE
        for k in range(n_generar):
            r = _ruta_osrm_buena(bbox, sleep)
            total_osrm += 1
            if r is not None:
                nuevas.append(r)
            if (k + 1) % 50 == 0:
                print(f"    …{k+1}/{n_generar} generadas con OSRM")
            time.sleep(sleep)

        nuevo_pool = rescatadas + nuevas
        if not nuevo_pool:
            print(f"  {sid}: pool vacío tras regenerar, conservo el actual")
            continue

        # Reasignar el pool a todos los vehículos de la sucursal
        for i, vid in enumerate(veh):
            rutas[vid] = nuevo_pool[i % len(nuevo_pool)]

        # Guardar tras CADA sucursal (resiliente si se corta a medias)
        json.dump(rutas, open(SALIDA, "w", encoding="utf-8"))
        print(f"  {sid}: pool final {len(nuevo_pool)} "
              f"({len(rescatadas)} rescatadas + {len(nuevas)} OSRM) → guardado")

    print(f"\nListo. Total llamadas OSRM: {total_osrm:,}. Guardado en {SALIDA}")


if __name__ == "__main__":
    main()
