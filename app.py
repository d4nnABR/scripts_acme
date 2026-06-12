import os
import sys
import json
import time
from dotenv import load_dotenv
from generator.catalog import generar_catalogo, cargar_catalogo
from generator.routes import cargar_o_generar_rutas
from generator.vehicle import Vehicle
from generator.kafka_client import (
    crear_schema_registry_client, crear_producer_gps,
    crear_producer_status, crear_producer_dlq,
    hacer_delivery_report, TOPIC_GPS, TOPIC_STATUS,
)

load_dotenv()

CATALOG_PATH = "catalog.json"
ROUTES_PATH  = "routes.json"
OFFLINE_UMBRAL_M = 800  # metros entre waypoints para trigger offline
N_OPERADORES = 3

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
    # Reparto entre operadores: python app.py [1|2|3] — sin argumento corre toda la flota
    parte = 0
    if len(sys.argv) > 1:
        try:
            parte = int(sys.argv[1])
        except ValueError:
            parte = -1
        if not 1 <= parte <= N_OPERADORES:
            raise SystemExit(f"Uso: python app.py [1-{N_OPERADORES}]")

    required = ["KAFKA_BOOTSTRAP_SERVER", "KAFKA_API_KEY", "KAFKA_API_SECRET",
                "SCHEMA_REGISTRY_URL", "SCHEMA_REGISTRY_API_KEY", "SCHEMA_REGISTRY_API_SECRET"]
    faltantes = [v for v in required if not os.getenv(v)]
    if faltantes:
        raise EnvironmentError(f"Faltan variables en .env: {', '.join(faltantes)}")

    # Cargar o generar catálogo
    try:
        catalogo = cargar_catalogo(CATALOG_PATH)
        print(f"Catálogo cargado desde {CATALOG_PATH}")
    except FileNotFoundError:
        print("Generando catálogo sintético...")
        catalogo = generar_catalogo()
        with open(CATALOG_PATH, "w", encoding="utf-8") as f:
            json.dump(catalogo, f, ensure_ascii=False, indent=2)

    # Cargar o generar rutas
    api_key    = os.getenv("GOOGLE_MAPS_API_KEY")
    route_mode = os.getenv("ROUTE_MODE", "pregenerated")
    if route_mode == "pregenerated":
        rutas = cargar_o_generar_rutas(ROUTES_PATH, catalogo, api_key)
    else:
        print("ROUTE_MODE=realtime — rutas se generarán en tiempo real (no implementado en demo)")
        rutas = cargar_o_generar_rutas(ROUTES_PATH, catalogo, api_key)

    # Crear producers Kafka
    sr_client       = crear_schema_registry_client()
    producer_gps    = crear_producer_gps(sr_client)
    producer_status = crear_producer_status(sr_client)
    producer_dlq    = crear_producer_dlq()

    # Inicializar vehículos
    suc_map = {s["id_sucursal"]: s for s in catalogo["sucursales"]}
    vehiculos: list[Vehicle] = []
    for v in catalogo["vehiculos"]:
        ruta = rutas.get(v["id_vehiculo"], [])
        if not ruta:
            continue
        vehiculos.append(Vehicle(v["id_vehiculo"], ruta, v["id_sucursal"]))

    # Módulo N para que cada operador cubra todas las sucursales
    if parte:
        vehiculos = [v for i, v in enumerate(vehiculos) if i % N_OPERADORES == parte - 1]
        print(f"Operador {parte}/{N_OPERADORES}")

    print(f"Iniciando simulación: {len(vehiculos)} vehículos\n")
    contadores = {"gps": 0, "estado": 0, "errores": 0, "dlq": 0}
    segundos = 0
    metricas_ts = 0

    try:
        while True:
            for v in vehiculos:
                v.tick(1.0)

                # Lógica offline
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

                # Publicar GPS cada 30s
                if segundos % 30 == 0:
                    dato = v.generar_gps()
                    if v.offline:
                        v.buffer.append(dato)
                    else:
                        dr = hacer_delivery_report(producer_dlq, TOPIC_GPS, v.id_vehiculo, dato)
                        producer_gps.produce(topic=TOPIC_GPS, key=v.id_vehiculo, value=dato, on_delivery=dr)
                        contadores["gps"] += 1

                # Publicar Estado cada 60s
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

            # Métricas cada 60s
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
