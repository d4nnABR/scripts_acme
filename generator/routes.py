import json
import math
import random
import time
import requests

MAPS_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

def _punto_aleatorio_en_bbox(bbox: dict) -> tuple[float, float]:
    lat = random.uniform(bbox["lat_min"], bbox["lat_max"])
    lon = random.uniform(bbox["lon_min"], bbox["lon_max"])
    return round(lat, 6), round(lon, 6)

def _decode_polyline(encoded: str) -> list[dict]:
    coords, idx, lat, lng = [], 0, 0, 0
    while idx < len(encoded):
        for is_lat in (True, False):
            result, shift, b = 0, 0, 0
            while True:
                b = ord(encoded[idx]) - 63
                idx += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            val = ~(result >> 1) if result & 1 else result >> 1
            if is_lat:
                lat += val
            else:
                lng += val
        coords.append({"lat": lat / 1e5, "lng": lng / 1e5})
    return coords

def _parsear_ruta(respuesta: dict) -> list[dict]:
    if not respuesta.get("routes"):
        raise ValueError("Google Maps no devolvió rutas")
    puntos = []
    for step in respuesta["routes"][0]["legs"][0]["steps"]:
        puntos.extend(_decode_polyline(step["polyline"]["encodedPolyline"]))
    return puntos

def _llamar_maps(origen: tuple, destino: tuple, api_key: str) -> list[dict]:
    payload = {
        "origin":      {"location": {"latLng": {"latitude": origen[0],  "longitude": origen[1]}}},
        "destination": {"location": {"latLng": {"latitude": destino[0], "longitude": destino[1]}}},
        "travelMode":  "DRIVE",
        "routingPreference": "TRAFFIC_UNAWARE",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.legs.steps.polyline",
    }
    for intento in range(5):
        r = requests.post(MAPS_ROUTES_URL, json=payload, headers=headers, timeout=10)
        if r.status_code == 429:
            time.sleep(5 * 2 ** intento)
            continue
        r.raise_for_status()
        return _parsear_ruta(r.json())
    r.raise_for_status()

def generar_rutas(catalogo: dict, api_key: str) -> dict:
    """Rutas reales con Google Maps. Solo para el catálogo base de 300 vehículos."""
    sucursal_map = {s["id_sucursal"]: s for s in catalogo["sucursales"]}
    rutas = {}
    total = len(catalogo["vehiculos"])
    for i, v in enumerate(catalogo["vehiculos"], 1):
        bbox = sucursal_map[v["id_sucursal"]]["bbox"]
        origen = _punto_aleatorio_en_bbox(bbox)
        destino = _punto_aleatorio_en_bbox(bbox)
        try:
            puntos = _llamar_maps(origen, destino, api_key)
            rutas[v["id_vehiculo"]] = puntos
            print(f"  [{i}/{total}] {v['id_vehiculo']} — {len(puntos)} waypoints")
        except Exception as e:
            print(f"  [{i}/{total}] {v['id_vehiculo']} — ERROR: {e}, usando ruta sintética")
            rutas[v["id_vehiculo"]] = _ruta_sintetica(bbox)
        time.sleep(0.6)
    return rutas

def _ruta_sintetica(bbox: dict, n_waypoints: int = 80) -> list[dict]:
    """Ruta sintética suave: muchos waypoints cortos con inercia de dirección.

    En vez de saltar al azar (zigzag), avanza en pasos pequeños (~40 m) girando
    solo un poco cada vez, así la trayectoria es una curva continua parecida a
    seguir una calle. Rebota en los bordes de la bbox para no salirse de ciudad.
    """
    PASO = 0.0004          # ~40 m por waypoint, similar a Google (~50 m)
    GIRO_MAX = 0.35        # radianes: cuánto puede girar entre pasos (suavidad)
    puntos = []
    lat = random.uniform(bbox["lat_min"], bbox["lat_max"])
    lon = random.uniform(bbox["lon_min"], bbox["lon_max"])
    rumbo = random.uniform(0, 2 * math.pi)
    for _ in range(n_waypoints):
        rumbo += random.uniform(-GIRO_MAX, GIRO_MAX)
        lat += PASO * math.cos(rumbo)
        lon += PASO * math.sin(rumbo)
        # Rebote: si toca el borde, invierte rumbo en lugar de pegarse a la pared
        if not (bbox["lat_min"] <= lat <= bbox["lat_max"]):
            lat = max(bbox["lat_min"], min(bbox["lat_max"], lat))
            rumbo = math.pi - rumbo
        if not (bbox["lon_min"] <= lon <= bbox["lon_max"]):
            lon = max(bbox["lon_min"], min(bbox["lon_max"], lon))
            rumbo = -rumbo
        puntos.append({"lat": round(lat, 6), "lng": round(lon, 6)})
    return puntos

def generar_rutas_sinteticas(catalogo: dict) -> dict:
    """Genera rutas sintéticas para toda la flota sin llamar a Google Maps."""
    sucursal_map = {s["id_sucursal"]: s for s in catalogo["sucursales"]}
    rutas = {}
    total = len(catalogo["vehiculos"])
    for i, v in enumerate(catalogo["vehiculos"], 1):
        bbox = sucursal_map[v["id_sucursal"]]["bbox"]
        rutas[v["id_vehiculo"]] = _ruta_sintetica(bbox)
        if i % 1000 == 0 or i == total:
            print(f"  Rutas sintéticas: {i:,}/{total:,}")
    return rutas

def cargar_o_generar_rutas(path: str, catalogo: dict | None, api_key: str | None) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            rutas = json.load(f)
            print(f"Rutas cargadas desde {path}")
    except FileNotFoundError:
        rutas = {}

    faltantes = [v for v in catalogo["vehiculos"] if v["id_vehiculo"] not in rutas] if catalogo else []
    if not faltantes:
        return rutas

    n_total = len(catalogo["vehiculos"])
    usar_maps = api_key and n_total <= 300

    if usar_maps:
        print(f"Generando rutas con Google Maps ({len(faltantes)} vehículos)...")
        nuevas = generar_rutas({"sucursales": catalogo["sucursales"], "vehiculos": faltantes}, api_key)
    else:
        print(f"Generando rutas sintéticas ({len(faltantes):,} vehículos — sin Google Maps)...")
        nuevas = generar_rutas_sinteticas({"sucursales": catalogo["sucursales"], "vehiculos": faltantes})

    rutas.update(nuevas)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rutas, f)
    print(f"Rutas guardadas en {path}")
    return rutas
