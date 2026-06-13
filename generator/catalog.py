import json
import random
import unicodedata
import requests
from datetime import date, timedelta

SUCURSALES = [
    {"id_sucursal": "SUC-001", "nombre_sucursal": "ACME Guatemala",  "pais": "Guatemala",   "ciudad": "Ciudad de Guatemala", "bbox": {"lat_min": 14.55, "lat_max": 14.75, "lon_min": -90.65, "lon_max": -90.45}},
    {"id_sucursal": "SUC-002", "nombre_sucursal": "ACME México",     "pais": "México",      "ciudad": "Ciudad de México",    "bbox": {"lat_min": 19.25, "lat_max": 19.55, "lon_min": -99.25, "lon_max": -99.05}},
    {"id_sucursal": "SUC-003", "nombre_sucursal": "ACME Colombia",   "pais": "Colombia",    "ciudad": "Bogotá",              "bbox": {"lat_min":  4.55, "lat_max":  4.75, "lon_min": -74.15, "lon_max": -74.00}},
    {"id_sucursal": "SUC-004", "nombre_sucursal": "ACME Chile",      "pais": "Chile",       "ciudad": "Santiago",            "bbox": {"lat_min": -33.55, "lat_max": -33.35, "lon_min": -70.75, "lon_max": -70.55}},
    {"id_sucursal": "SUC-005", "nombre_sucursal": "ACME Perú",       "pais": "Perú",        "ciudad": "Lima",                "bbox": {"lat_min": -12.15, "lat_max": -11.95, "lon_min": -77.10, "lon_max": -76.95}},
    {"id_sucursal": "SUC-006", "nombre_sucursal": "ACME Argentina",  "pais": "Argentina",   "ciudad": "Buenos Aires",        "bbox": {"lat_min": -34.70, "lat_max": -34.52, "lon_min": -58.55, "lon_max": -58.33}},
    {"id_sucursal": "SUC-007", "nombre_sucursal": "ACME Ecuador",    "pais": "Ecuador",     "ciudad": "Quito",               "bbox": {"lat_min":  -0.30, "lat_max":  -0.10, "lon_min": -78.60, "lon_max": -78.42}},
    {"id_sucursal": "SUC-008", "nombre_sucursal": "ACME Costa Rica", "pais": "Costa Rica",  "ciudad": "San José",            "bbox": {"lat_min":  9.88, "lat_max": 10.05, "lon_min": -84.18, "lon_max": -84.00}},
    {"id_sucursal": "SUC-009", "nombre_sucursal": "ACME Panamá",     "pais": "Panamá",      "ciudad": "Ciudad de Panamá",    "bbox": {"lat_min":  8.95, "lat_max":  9.12, "lon_min": -79.60, "lon_max": -79.42}},
    {"id_sucursal": "SUC-010", "nombre_sucursal": "ACME Honduras",   "pais": "Honduras",    "ciudad": "Tegucigalpa",         "bbox": {"lat_min": 14.05, "lat_max": 14.18, "lon_min": -87.28, "lon_max": -87.14}},
]

MODELOS = ["ACME Volt S", "ACME Volt X", "ACME Urban E",
           "ACME Cargo V", "ACME Trail P", "ACME Aero R"]

NOMBRES = ["Ana", "Carlos", "María", "José", "Laura", "Pedro", "Sofía", "Diego",
           "Valentina", "Andrés", "Lucía", "Miguel", "Camila", "Jorge", "Daniela",
           "Fernando", "Gabriela", "Ricardo", "Isabela", "Manuel", "Paola", "Héctor",
           "Mariana", "Óscar", "Regina"]
APELLIDOS = ["García", "López", "Martínez", "Rodríguez", "Hernández", "González",
             "Pérez", "Flores", "Castro", "Morales", "Ramírez", "Torres", "Vargas",
             "Mendoza", "Rojas", "Aguilar", "Ortiz", "Silva", "Núñez", "Campos"]
DOMINIOS = ["gmail.com", "outlook.com", "hotmail.com", "yahoo.com"]

def _fecha_aleatoria() -> str:
    inicio = date(2022, 1, 1)
    dias = random.randint(0, (date(2024, 12, 31) - inicio).days)
    return str(inicio + timedelta(days=dias))

def _sin_acentos(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()

def obtener_clientes_api(n: int = 100) -> list[dict]:
    """Personas falsas realistas desde randomuser.me (nombres hispanos)."""
    r = requests.get("https://randomuser.me/api/", params={
        "results": n * 2,  # margen para deduplicar
        "nat": "es,mx",
        "inc": "name,email",
        "noinfo": "",
    }, timeout=15)
    r.raise_for_status()
    clientes, vistos = [], set()
    for u in r.json()["results"]:
        nombre = f"{u['name']['first']} {u['name']['last']}"
        if nombre in vistos:
            continue
        vistos.add(nombre)
        usuario = u["email"].split("@")[0]
        clientes.append({"nombre": nombre, "correo": f"{usuario}@{random.choice(DOMINIOS)}"})
        if len(clientes) == n:
            break
    if len(clientes) < n:
        raise ValueError(f"randomuser.me devolvió solo {len(clientes)} nombres únicos")
    return clientes

def _clientes_fallback(n: int = 100) -> list[dict]:
    """Sin internet: combinaciones únicas nombre + 2 apellidos (500+ combos)."""
    combos = [(no, a1, a2) for no in NOMBRES for a1 in APELLIDOS for a2 in APELLIDOS if a1 != a2]
    random.shuffle(combos)
    clientes = []
    for i, (no, a1, a2) in enumerate(combos[:n], 1):
        nombre = f"{no} {a1} {a2}"
        # índice único en el correo: evita colisiones entre tocayos
        correo = f"{_sin_acentos(no)}.{_sin_acentos(a1)}{i:02d}@{random.choice(DOMINIOS)}"
        clientes.append({"nombre": nombre, "correo": correo})
    return clientes

def generar_catalogo(usar_api: bool = True) -> dict:
    # 100 personas únicas: randomuser.me si hay red, fallback local si no
    personas = None
    if usar_api:
        try:
            personas = obtener_clientes_api(100)
            print("Clientes generados con randomuser.me")
        except Exception as e:
            print(f"randomuser.me no disponible ({e}) — usando fallback local")
    if personas is None:
        personas = _clientes_fallback(100)

    vehiculos, clientes, asignaciones = [], [], []
    for i in range(1, 101):
        suc_idx = (i - 1) // 10
        id_v = f"EV-ACME-{i:05d}"
        id_c = f"CLI-{i:05d}"
        vehiculos.append({
            "id_vehiculo": id_v,
            "modelo": random.choice(MODELOS),
            "anio": random.choice([2022, 2023, 2024]),
            "id_sucursal": SUCURSALES[suc_idx]["id_sucursal"],
        })
        clientes.append({
            "id_cliente": id_c,
            "nombre_cliente": personas[i - 1]["nombre"],
            "correo": personas[i - 1]["correo"],
        })
        asignaciones.append({
            "id_cliente": id_c,
            "id_vehiculo": id_v,
            "fecha_asignacion": _fecha_aleatoria(),
        })

    return {"sucursales": SUCURSALES, "vehiculos": vehiculos, "clientes": clientes, "cliente_vehiculo": asignaciones}

def extender_catalogo(catalogo: dict, n_total: int, usar_api: bool = True) -> dict:
    """Agrega vehículos hasta n_total sin tocar los existentes."""
    actuales = len(catalogo["vehiculos"])
    nuevos = n_total - actuales
    if nuevos <= 0:
        return catalogo

    personas = None
    if usar_api:
        try:
            personas = obtener_clientes_api(nuevos)
            print(f"{nuevos} clientes nuevos generados con randomuser.me")
        except Exception as e:
            print(f"randomuser.me no disponible ({e}) — usando fallback local")
    if personas is None:
        personas = _clientes_fallback(nuevos)

    for j, i in enumerate(range(actuales + 1, n_total + 1)):
        suc_idx = (i - 1) % len(SUCURSALES)
        id_v = f"EV-ACME-{i:05d}"
        id_c = f"CLI-{i:05d}"
        catalogo["vehiculos"].append({
            "id_vehiculo": id_v,
            "modelo": random.choice(MODELOS),
            "anio": random.choice([2022, 2023, 2024]),
            "id_sucursal": SUCURSALES[suc_idx]["id_sucursal"],
        })
        catalogo["clientes"].append({
            "id_cliente": id_c,
            "nombre_cliente": personas[j]["nombre"],
            "correo": personas[j]["correo"],
        })
        catalogo["cliente_vehiculo"].append({
            "id_cliente": id_c,
            "id_vehiculo": id_v,
            "fecha_asignacion": _fecha_aleatoria(),
        })
    return catalogo

def generar_catalogo_n(n: int, usar_api: bool = True) -> dict:
    """Genera un catálogo fresco de exactamente n vehículos."""
    personas = None
    if usar_api:
        try:
            personas = obtener_clientes_api(min(n, 5000))
            print(f"  {len(personas)} clientes obtenidos de randomuser.me")
        except Exception as e:
            print(f"  randomuser.me no disponible ({e}) — usando fallback local")
    if personas is None:
        personas = _clientes_fallback(n)

    # si n > personas disponibles, completar con fallback extra
    while len(personas) < n:
        extra = _clientes_fallback(n - len(personas))
        personas += extra

    vehiculos, clientes, asignaciones = [], [], []
    for i in range(1, n + 1):
        suc_idx = (i - 1) % len(SUCURSALES)
        id_v = f"EV-ACME-{i:05d}"
        id_c = f"CLI-{i:05d}"
        vehiculos.append({
            "id_vehiculo": id_v,
            "modelo":      random.choice(MODELOS),
            "anio":        random.choice([2022, 2023, 2024]),
            "id_sucursal": SUCURSALES[suc_idx]["id_sucursal"],
        })
        clientes.append({
            "id_cliente":     id_c,
            "nombre_cliente": personas[i - 1]["nombre"],
            "correo":         personas[i - 1]["correo"],
        })
        asignaciones.append({
            "id_cliente":       id_c,
            "id_vehiculo":      id_v,
            "fecha_asignacion": _fecha_aleatoria(),
        })
    return {"sucursales": SUCURSALES, "vehiculos": vehiculos,
            "clientes": clientes, "cliente_vehiculo": asignaciones}

def cargar_catalogo(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
