import hashlib
import random
from datetime import datetime, UTC
from generator.physics import haversine_km, bearing_deg, delta_bearing, speed_kmh

BATERIA_DESCARGA_POR_KM = 0.5
BATERIA_MINIMA = 5.0

# Códigos de falla del catálogo (catalog_csv/codigos_falla.csv).
# El generador solo emite estos códigos para que coincidan con el catálogo.
CODIGOS_FALLA = [
    101, 102, 103, 104, 105, 106, 107, 108, 109, 110,  # batería
    201, 202, 203, 204, 205, 206, 207, 208, 209,       # motor
    301, 302, 303, 304, 305, 306, 307, 308,            # frenos
    401, 402, 403, 404, 405, 406, 407, 408,            # sensores
    501, 502, 503, 504, 505, 506, 507,                 # carga
    601, 602, 603, 604, 605, 606, 607,                 # chasis
    701, 702, 703, 704,                                # hvac
    801, 802, 803, 804, 805,                           # eléctrico
    901, 902, 903, 904, 905,                           # software
]

def _odometro_base(id_vehiculo: str) -> int:
    # Determinístico por id: el odómetro de vida no cambia entre reinicios
    # del generador (8,000–90,000 km)
    h = int(hashlib.md5(id_vehiculo.encode()).hexdigest()[:8], 16)
    return 8_000 + h % 82_000

def _ts() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

class Vehicle:
    def __init__(self, id_vehiculo: str, ruta: list[dict], sucursal: str):
        self.id_vehiculo = id_vehiculo
        self.sucursal = sucursal
        self.ruta = ruta
        self.ruta_idx = 0
        self.lat = ruta[0]["lat"]
        self.lon = ruta[0]["lng"]
        self.prev_bearing = 0.0

        self.on_off = 1
        self.estado_carga = float(random.randint(40, 100))
        self.kilometros = _odometro_base(id_vehiculo)
        self.codigo_falla = 0
        self.km_acumulados_sesion = 0.0

        self.offline = False
        self.offline_since: str | None = None
        self.offline_duration_s: int = 0
        self.offline_elapsed_s: int = 0
        self.buffer: list[dict] = []

    def tick(self, segundos: float = 1.0):
        if self.ruta_idx >= len(self.ruta) - 1:
            # Reinicio de ruta: el vehículo reaparece en el punto de partida.
            # Sin este reset quedaría en el fin y avanzaría en línea recta
            # hacia el inicio (off-road) durante minutos — en el mapa se ve
            # como carros congelados que saltan cada trama
            self.ruta_idx = 0
            self.lat = self.ruta[0]["lat"]
            self.lon = self.ruta[0]["lng"]
            self._recargar()
            return

        siguiente = self.ruta[self.ruta_idx + 1]
        curr_bearing = bearing_deg(self.lat, self.lon, siguiente["lat"], siguiente["lng"])
        delta = delta_bearing(self.prev_bearing, curr_bearing)
        velocidad = speed_kmh(delta)

        distancia_tick = velocidad * (segundos / 3600.0)
        distancia_hasta_siguiente = haversine_km(self.lat, self.lon, siguiente["lat"], siguiente["lng"])

        if distancia_tick >= distancia_hasta_siguiente:
            self.lat = siguiente["lat"]
            self.lon = siguiente["lng"]
            self.ruta_idx += 1
            d = distancia_hasta_siguiente
        else:
            ratio = distancia_tick / max(distancia_hasta_siguiente, 0.0001)
            self.lat += (siguiente["lat"] - self.lat) * ratio
            self.lon += (siguiente["lng"] - self.lon) * ratio
            d = distancia_tick

        self.prev_bearing = curr_bearing
        self._actualizar_bateria(d)
        self.km_acumulados_sesion += d
        self.kilometros += d
        self._actualizar_falla()

        if self.offline:
            self.offline_elapsed_s += int(segundos)

    def _actualizar_bateria(self, km: float):
        self.estado_carga = max(BATERIA_MINIMA, self.estado_carga - km * BATERIA_DESCARGA_POR_KM)

    def _recargar(self):
        self.estado_carga = min(100.0, self.estado_carga + random.uniform(40, 80))
        self.km_acumulados_sesion = 0.0

    def _actualizar_falla(self):
        if random.random() < 0.001:
            self.codigo_falla = random.choice(CODIGOS_FALLA)
        elif random.random() < 0.01 and self.codigo_falla > 0:
            self.codigo_falla = 0

    def generar_gps(self) -> dict:
        return {
            "id_vehiculo": self.id_vehiculo,
            "timestamp": _ts(),
            "tipo_trama": "GPS",
            "telemetria": {
                "latitud": round(self.lat, 6),
                "longitud": round(self.lon, 6),
            },
        }

    def generar_estado(self) -> dict:
        return {
            "id_vehiculo": self.id_vehiculo,
            "timestamp": _ts(),
            "tipo_trama": "ESTADO",
            "telemetria": {
                "estado_carga": int(self.estado_carga),
                "on_off": self.on_off,
                "codigo_falla": self.codigo_falla,
                "kilometros": int(self.kilometros),
            },
        }

    def entrar_offline(self):
        self.offline = True
        self.offline_since = _ts()
        self.offline_duration_s = random.randint(120, 240)
        self.offline_elapsed_s = 0
        self.buffer = []

    def reconectar(self) -> list[dict]:
        offline_hasta = _ts()
        tramas = list(self.buffer)
        # Los campos de reconexión solo existen en el schema ESTADO:
        # se marca la última trama ESTADO del buffer, no la última en general
        for trama in reversed(tramas):
            if trama.get("tipo_trama") == "ESTADO":
                trama["reconexion"] = True
                trama["offline_desde"] = self.offline_since
                trama["offline_hasta"] = offline_hasta
                trama["tramas_buffereadas"] = len(tramas)
                break
        self.offline = False
        self.offline_since = None
        self.buffer = []
        return tramas
