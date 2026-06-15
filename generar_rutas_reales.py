"""Genera un pool de rutas REALES de Google Maps y las reúsa para toda la flota.

Estrategia para no agotar la cuota gratis:
  - Genera N_POOL rutas reales POR SUCURSAL (siguen calles de verdad).
  - Las reúsa en bucle entre los vehículos de esa misma sucursal.
  - Reparte las llamadas entre dos API keys.

Las API keys se leen del entorno / .env (NUNCA hardcodeadas en el repo):
    GOOGLE_MAPS_API_KEY     → key principal (primeras LIMITE_KEY_A llamadas)
    GOOGLE_MAPS_API_KEY_2   → key secundaria (resto). Opcional: si falta, usa solo la principal.

Uso:
    python generar_rutas_reales.py
"""
import os
import json
import time
import random

from dotenv import load_dotenv

from generator.routes import (
    _llamar_maps, _punto_aleatorio_en_bbox, _ruta_sintetica, _ruta_sobre_calles,
)
from generator.catalog import cargar_catalogo

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
CATALOGO = "catalog_10000.json"
SALIDA   = "routes_10000.json"

# Dos keys para repartir el consumo (desde .env). La primera cubre LIMITE_KEY_A
# llamadas, la segunda el resto. Si solo hay una, se usa esa para todo.
API_KEY_A    = os.getenv("GOOGLE_MAPS_API_KEY")
API_KEY_B    = os.getenv("GOOGLE_MAPS_API_KEY_2") or API_KEY_A
# Repartir la mitad de las llamadas a cada key (si hay segunda key), para no
# agotar la cuota gratis de una sola. Con 8000 rutas → ~4000 por key.
LIMITE_KEY_A = 4000

# Total de rutas reales a generar (se reparten entre las 10 sucursales).
# 8000 rutas / 10 sucursales = 800 rutas reales por ciudad.
TOTAL_POOL = 8000

# Si la ruta de Google cruza agua (salto largo entre waypoints), se reintenta
# con otro par de puntos hasta MAX_REINTENTOS_MAR veces antes de aceptar/caer
# a sintética. Evita los "carros en el mar" en ciudades costeras (Panamá).
MAX_REINTENTOS_MAR = 4


def _key_para(llamada_idx: int) -> str:
    return API_KEY_A if llamada_idx < LIMITE_KEY_A else API_KEY_B


def main():
    if not API_KEY_A:
        raise SystemExit(
            "Falta GOOGLE_MAPS_API_KEY en el .env.\n"
            "Agrega tu key (y opcionalmente GOOGLE_MAPS_API_KEY_2) antes de correr."
        )
    catalogo = cargar_catalogo(CATALOGO)
    sucursales = catalogo["sucursales"]
    suc_map = {s["id_sucursal"]: s for s in sucursales}

    # Vehículos agrupados por sucursal
    por_sucursal: dict[str, list[str]] = {}
    for v in catalogo["vehiculos"]:
        por_sucursal.setdefault(v["id_sucursal"], []).append(v["id_vehiculo"])

    pool_por_suc = max(1, TOTAL_POOL // len(sucursales))
    print(f"Generando {pool_por_suc} rutas reales por sucursal "
          f"({pool_por_suc * len(sucursales):,} llamadas a Google)…\n")

    rutas: dict[str, list] = {}
    llamada = 0
    n_reales = 0      # rutas que quedaron sobre calles
    n_sinteticas = 0  # fallbacks por error o por no encontrar ruta en tierra

    for s in sucursales:
        sid  = s["id_sucursal"]
        bbox = s["bbox"]
        veh  = por_sucursal.get(sid, [])
        if not veh:
            continue

        # 1) Pool de rutas reales para esta sucursal
        pool = []
        suc_sint = 0
        for _ in range(min(pool_por_suc, len(veh))):
            # Reintentar con otro par de puntos si la ruta cruza agua (mar).
            puntos = None
            for reintento in range(MAX_REINTENTOS_MAR):
                origen  = _punto_aleatorio_en_bbox(bbox)
                destino = _punto_aleatorio_en_bbox(bbox)
                key = _key_para(llamada)
                llamada += 1
                try:
                    cand = _llamar_maps(origen, destino, key)
                except Exception as e:
                    if reintento == MAX_REINTENTOS_MAR - 1:
                        print(f"  {sid} llamada {llamada}: ERROR {e} → ruta sintética")
                    time.sleep(0.6)
                    continue
                if _ruta_sobre_calles(cand):
                    puntos = cand
                    break
                # cayó en agua: descartar y reintentar con otro punto
                time.sleep(0.6)

            if puntos is not None:
                pool.append(puntos); n_reales += 1
            else:
                pool.append(_ruta_sintetica(bbox)); n_sinteticas += 1; suc_sint += 1

            if llamada % 100 == 0:
                print(f"  …{llamada:,} llamadas (key {'A' if llamada < LIMITE_KEY_A else 'B'})")
            time.sleep(0.6)

        # 2) Reusar el pool en bucle entre los vehículos de la sucursal
        for i, id_v in enumerate(veh):
            rutas[id_v] = pool[i % len(pool)]
        print(f"  {sid}: {len(pool)} rutas en pool ({suc_sint} sintéticas) "
              f"→ reusadas en {len(veh):,} vehículos")

    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(rutas, f)
    print(f"\nListo: {len(rutas):,} vehículos con rutas en {SALIDA}")
    print(f"Rutas reales (sobre calles): {n_reales:,}  |  Fallbacks sintéticos: {n_sinteticas:,}")
    print(f"Total llamadas a Google: {llamada:,}")


if __name__ == "__main__":
    main()
