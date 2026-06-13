import os
import sys
import json
import time
from dotenv import load_dotenv
from generator.catalog import generar_catalogo, generar_catalogo_n, cargar_catalogo
from generator.routes import cargar_o_generar_rutas
from generator.vehicle import Vehicle
from generator.kafka_client import (
    crear_schema_registry_client, crear_producer_gps,
    crear_producer_status, crear_producer_dlq,
    hacer_delivery_report, TOPIC_GPS, TOPIC_STATUS,
)

load_dotenv()

OFFLINE_UMBRAL_M = 800
N_OPERADORES = 3

OPCIONES_FLOTA = {
    "1": 300,
    "2": 1_000,
    "3": 6_000,
    "4": 10_000,
}


# Catálogo maestro: si existe, todas las opciones del menú toman los primeros N
# de aquí (un solo archivo sirve para 300/1000/6000/10000). Si no existe, cae al
# catalog.json base de 300 incluido en el repo.
CATALOGO_MAESTRO = "catalog_10000.json"
ROUTES_MAESTRO   = "routes_10000.json"  # rutas reales (pool de Google) para todo el maestro

def _recortar(catalogo: dict, n: int) -> dict:
    """Devuelve un catálogo con solo los primeros n vehículos y sus clientes/asignaciones."""
    veh = catalogo["vehiculos"][:n]
    ids = {v["id_vehiculo"] for v in veh}
    return {
        "sucursales":       catalogo["sucursales"],
        "vehiculos":        veh,
        "clientes":         catalogo["clientes"][:n],
        "cliente_vehiculo": [a for a in catalogo["cliente_vehiculo"] if a["id_vehiculo"] in ids],
    }


def _menu_flota() -> int:
    print("\n══════════════════════════════════════════════")
    print("  ACME EV — Generador de telemetría")
    print("══════════════════════════════════════════════")
    print("  ¿Cuántos vehículos quieres simular?\n")
    print("  [1]    300  vehículos  (demo — incluido en el repo)")
    print("  [2]  1,000  vehículos")
    print("  [3]  6,000  vehículos")
    print("  [4] 10,000  vehículos")
    print()
    while True:
        eleccion = input("  Opción [1-4]: ").strip()
        if eleccion in OPCIONES_FLOTA:
            return OPCIONES_FLOTA[eleccion]
        print("  Ingresa 1, 2, 3 o 4.")


def _menu_operador() -> int:
    print()
    print("  ¿Qué parte de la flota corres tú?\n")
    print("  [1]  Operador 1  (primer tercio)")
    print("  [2]  Operador 2  (segundo tercio)")
    print("  [3]  Operador 3  (tercer tercio)")
    print("  [0]  Toda la flota  (solo demo / pruebas locales)")
    print()
    while True:
        eleccion = input("  Operador [0-3]: ").strip()
        if eleccion in ("0", "1", "2", "3"):
            return int(eleccion)
        print("  Ingresa 0, 1, 2 o 3.")


def _cargar_o_crear_catalogo(n: int, api_key: str | None) -> tuple[dict, dict]:
    # ── catálogo ──────────────────────────────────────────────────────────────
    if os.path.exists(CATALOGO_MAESTRO):
        completo = cargar_catalogo(CATALOGO_MAESTRO)
        disponibles = len(completo["vehiculos"])
        if n > disponibles:
            print(f"  Aviso: el maestro tiene {disponibles:,} vehículos; se usarán todos.")
            n = disponibles
        catalogo = _recortar(completo, n)
        print(f"Catálogo: primeros {n:,} de {CATALOGO_MAESTRO} ({disponibles:,} disponibles)")
        # routes_10000.json (rutas reales del pool) cubre los IDs de cualquier N,
        # porque el recorte toma los primeros N vehículos del mismo maestro.
        routes_path = ROUTES_MAESTRO if os.path.exists(ROUTES_MAESTRO) else f"routes_{n}.json"
    elif n == 300:
        # Respaldo: el repo trae catalog.json + routes.json con 300 reales
        catalogo = cargar_catalogo("catalog.json")
        print(f"Catálogo cargado desde catalog.json  ({len(catalogo['vehiculos']):,} vehículos)")
        routes_path = "routes.json"
    else:
        print(f"\nGenerando catálogo de {n:,} vehículos (primera vez — puede tardar)…")
        catalogo = generar_catalogo_n(n)
        cat_path = f"catalog_{n}.json"
        with open(cat_path, "w", encoding="utf-8") as f:
            json.dump(catalogo, f, ensure_ascii=False, indent=2)
        print(f"  Guardado en {cat_path}")
        routes_path = f"routes_{n}.json"

    # ── rutas ─────────────────────────────────────────────────────────────────
    rutas = cargar_o_generar_rutas(routes_path, catalogo, api_key)
    return catalogo, rutas


def _distancia_m(ruta: list[dict], idx: int) -> float:
    from generator.physics import haversine_km
    if idx >= len(ruta) - 1:
        return 0.0
    a, b = ruta[idx], ruta[idx + 1]
    return haversine_km(a["lat"], a["lng"], b["lat"], b["lng"]) * 1000


def _imprimir_metricas(vehiculos: list[Vehicle], contadores: dict):
    activos  = sum(1 for v in vehiculos if v.on_off == 1 and not v.offline)
    offline  = sum(1 for v in vehiculos if v.offline)
    apagados = sum(1 for v in vehiculos if v.on_off == 0)
    print(f"\n[Metrics] ── ACME EV ──────────────────────────")
    print(f"  GPS events/min:      {contadores['gps']}")
    print(f"  Estado events/min:   {contadores['estado']}")
    print(f"  Vehículos activos:   {activos}")
    print(f"  Vehículos offline:   {offline}")
    print(f"  Vehículos apagados:  {apagados}")
    print(f"  Errores publicación: {contadores['errores']}")
    print(f"  DLQ mensajes:        {contadores['dlq']}")
    print(f"──────────────────────────────────────────────\n")
    contadores.update({"gps": 0, "estado": 0, "errores": 0})


def main():
    required = ["KAFKA_BOOTSTRAP_SERVER", "KAFKA_API_KEY", "KAFKA_API_SECRET",
                "SCHEMA_REGISTRY_URL", "SCHEMA_REGISTRY_API_KEY", "SCHEMA_REGISTRY_API_SECRET"]
    faltantes = [v for v in required if not os.getenv(v)]
    if faltantes:
        raise EnvironmentError(f"Faltan variables en .env: {', '.join(faltantes)}")

    n_flota = _menu_flota()
    parte   = _menu_operador()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    catalogo, rutas = _cargar_o_crear_catalogo(n_flota, api_key)

    # ── producers Kafka ───────────────────────────────────────────────────────
    sr_client       = crear_schema_registry_client()
    producer_gps    = crear_producer_gps(sr_client)
    producer_status = crear_producer_status(sr_client)
    producer_dlq    = crear_producer_dlq()

    # ── inicializar vehículos ─────────────────────────────────────────────────
    vehiculos: list[Vehicle] = []
    for v in catalogo["vehiculos"]:
        ruta = rutas.get(v["id_vehiculo"], [])
        if not ruta:
            continue
        vehiculos.append(Vehicle(v["id_vehiculo"], ruta, v["id_sucursal"]))

    if parte:
        vehiculos = [v for i, v in enumerate(vehiculos) if i % N_OPERADORES == parte - 1]
        print(f"\nOperador {parte}/{N_OPERADORES} — {len(vehiculos):,} vehículos asignados")
    else:
        print(f"\nModo completo — {len(vehiculos):,} vehículos")

    print("(Ctrl+C para detener)\n")

    contadores  = {"gps": 0, "estado": 0, "errores": 0, "dlq": 0}
    segundos    = 0
    metricas_ts = 0

    try:
        while True:
            for v in vehiculos:
                v.tick(1.0)

                # lógica offline
                if not v.offline:
                    dist = _distancia_m(v.ruta, v.ruta_idx) if v.ruta_idx < len(v.ruta) - 1 else 0
                    if dist > OFFLINE_UMBRAL_M and (hash(v.id_vehiculo + str(segundos)) % 50 == 0):
                        v.entrar_offline()
                        print(f"[OFFLINE] {v.id_vehiculo} sin señal desde {v.offline_since}")
                elif v.offline_elapsed_s >= v.offline_duration_s:
                    tramas = v.reconectar()
                    print(f"[RECONEX] {v.id_vehiculo} — liberando {len(tramas)} tramas")
                    for t in tramas:
                        if t["tipo_trama"] == "GPS":
                            dr = hacer_delivery_report(producer_dlq, TOPIC_GPS, v.id_vehiculo, t)
                            producer_gps.produce(topic=TOPIC_GPS, key=v.id_vehiculo, value=t, on_delivery=dr)
                            contadores["gps"] += 1
                        else:
                            dr = hacer_delivery_report(producer_dlq, TOPIC_STATUS, v.id_vehiculo, t)
                            producer_status.produce(topic=TOPIC_STATUS, key=v.id_vehiculo, value=t, on_delivery=dr)
                            contadores["estado"] += 1
                    producer_gps.poll(0)
                    producer_status.poll(0)
                    continue

                # publicar GPS cada 30s
                if segundos % 30 == 0:
                    dato = v.generar_gps()
                    if v.offline:
                        v.buffer.append(dato)
                    else:
                        dr = hacer_delivery_report(producer_dlq, TOPIC_GPS, v.id_vehiculo, dato)
                        producer_gps.produce(topic=TOPIC_GPS, key=v.id_vehiculo, value=dato, on_delivery=dr)
                        contadores["gps"] += 1

                # publicar Estado cada 60s
                if segundos % 60 == 0:
                    dato = v.generar_estado()
                    if v.offline:
                        v.buffer.append(dato)
                    else:
                        dr = hacer_delivery_report(producer_dlq, TOPIC_STATUS, v.id_vehiculo, dato)
                        producer_status.produce(topic=TOPIC_STATUS, key=v.id_vehiculo, value=dato, on_delivery=dr)
                        contadores["estado"] += 1

            producer_gps.poll(0)
            producer_status.poll(0)

            if segundos - metricas_ts >= 60:
                _imprimir_metricas(vehiculos, contadores)
                metricas_ts = segundos

            time.sleep(1)
            segundos += 1

    except KeyboardInterrupt:
        print("\nSimulación detenida.")
        producer_gps.flush()
        producer_status.flush()
        producer_dlq.flush()


if __name__ == "__main__":
    main()
