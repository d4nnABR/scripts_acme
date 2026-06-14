"""Construye routes_10000.json reusando las 300 rutas REALES de routes.json.

Google empezó a devolver 429 (cuota agotada) tras ~100 llamadas, así que en vez
de generar 3000 rutas nuevas, reusamos las 300 reales que ya existen (30 por
sucursal, ~288 waypoints c/u). Cada ruta real se asigna en bucle a los vehículos
de SU MISMA sucursal, para que todos sigan calles reales de su ciudad.

Uso:
    python reusar_rutas.py
"""
import json
import os

CAT_BASE   = "catalog.json"        # 300 vehículos → sucursal de cada ruta real
CAT_DESTINO = "catalog_10000.json" # 10k vehículos a los que asignar rutas
RUTAS_REALES = "routes.json"       # 300 rutas reales de Google
SALIDA      = "routes_10000.json"


def main():
    for p in (CAT_BASE, CAT_DESTINO, RUTAS_REALES):
        if not os.path.exists(p):
            raise SystemExit(f"Falta '{p}'.")

    cat_base = json.load(open(CAT_BASE, encoding="utf-8"))
    cat_dest = json.load(open(CAT_DESTINO, encoding="utf-8"))
    reales   = json.load(open(RUTAS_REALES, encoding="utf-8"))

    # Pool de rutas reales agrupadas por sucursal
    suc_base = {v["id_vehiculo"]: v["id_sucursal"] for v in cat_base["vehiculos"]}
    pool = {}  # id_sucursal → [rutas reales]
    for idv, ruta in reales.items():
        sid = suc_base.get(idv)
        if sid:
            pool.setdefault(sid, []).append(ruta)

    print("Rutas reales por sucursal:", {k: len(v) for k, v in sorted(pool.items())})

    # Asignar a los 10k: cada vehículo recibe una ruta real de su sucursal (bucle)
    contador = {}  # id_sucursal → índice rotatorio
    rutas_out = {}
    sin_pool = 0
    for v in cat_dest["vehiculos"]:
        sid = v["id_sucursal"]
        rutas_suc = pool.get(sid)
        if not rutas_suc:
            sin_pool += 1
            continue
        i = contador.get(sid, 0)
        rutas_out[v["id_vehiculo"]] = rutas_suc[i % len(rutas_suc)]
        contador[sid] = i + 1

    json.dump(rutas_out, open(SALIDA, "w", encoding="utf-8"))
    mb = os.path.getsize(SALIDA) / 1_048_576
    print(f"\n{SALIDA}: {len(rutas_out):,} vehículos con rutas reales, {mb:.1f} MB")
    if sin_pool:
        print(f"  (aviso: {sin_pool} vehículos sin pool de sucursal — omitidos)")
    reuso = len(rutas_out) / max(1, sum(len(v) for v in pool.values()))
    print(f"  Cada ruta real se reúsa ~{reuso:.0f} veces (dentro de su ciudad)")


if __name__ == "__main__":
    main()
