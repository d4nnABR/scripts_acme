import json
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
            print(f"  [{i}/{total}] {v['id_vehiculo']} — ERROR: {e}, usando ruta lineal")
            rutas[v["id_vehiculo"]] = [
                {"lat": origen[0], "lng": origen[1]},
                {"lat": destino[0], "lng": destino[1]},
            ]
        time.sleep(0.6)
    return rutas

def cargar_o_generar_rutas(path: str, catalogo: dict | None, api_key: str | None) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            rutas = json.load(f)
            print(f"Rutas cargadas desde {path}")
    except FileNotFoundError:
        rutas = {}

    # Incremental: solo genera rutas de vehículos que no tienen
    faltantes = [v for v in catalogo["vehiculos"] if v["id_vehiculo"] not in rutas] if catalogo else []
    if faltantes:
        print(f"Generando rutas reales con Google Maps ({len(faltantes)} vehículos)...")
        nuevas = generar_rutas({"sucursales": catalogo["sucursales"], "vehiculos": faltantes}, api_key)
        rutas.update(nuevas)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rutas, f)
        print(f"Rutas guardadas en {path}")
    return rutas
