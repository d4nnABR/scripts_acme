import pytest
from generator.vehicle import Vehicle

RUTA_CORTA = [
    {"lat": 14.6012, "lng": -90.5189},
    {"lat": 14.6020, "lng": -90.5180},
    {"lat": 14.6030, "lng": -90.5170},
]

def test_vehicle_estado_inicial():
    v = Vehicle("EV-ACME-00001", RUTA_CORTA, sucursal="SUC-001")
    assert v.id_vehiculo == "EV-ACME-00001"
    assert v.on_off == 1
    assert 5 <= v.estado_carga <= 100
    assert v.offline is False
    # Odómetro de vida realista, no carro recién salido de fábrica
    assert 8_000 <= v.kilometros <= 90_000

def test_vehicle_odometro_deterministico_por_id():
    # Mismo vehículo → mismo odómetro base entre reinicios del generador
    a = Vehicle("EV-ACME-00042", RUTA_CORTA, sucursal="SUC-005")
    b = Vehicle("EV-ACME-00042", RUTA_CORTA, sucursal="SUC-005")
    assert a.kilometros == b.kilometros
    c = Vehicle("EV-ACME-00043", RUTA_CORTA, sucursal="SUC-005")
    assert a.kilometros != c.kilometros

def test_vehicle_avanza_posicion():
    v = Vehicle("EV-ACME-00001", RUTA_CORTA, sucursal="SUC-001")
    lat_inicial = v.lat
    v.tick(1.0)
    # Después de 1 segundo debe haber avanzado
    assert v.lat != lat_inicial or v.lon != -90.5189

def test_vehicle_reinicio_de_ruta_vuelve_al_inicio():
    # Al terminar la ruta el vehículo reaparece en el punto de partida —
    # sin el reset quedaría en el fin y cruzaría la ciudad en línea recta
    # (off-road), que el mapa muestra como carros congelados que saltan
    v = Vehicle("EV-ACME-00001", RUTA_CORTA, sucursal="SUC-001")
    for _ in range(10_000):
        idx_antes = v.ruta_idx
        v.tick(1.0)
        if v.ruta_idx == 0 and idx_antes != 0:
            break
    else:
        pytest.fail("la ruta nunca reinició")
    assert v.lat == RUTA_CORTA[0]["lat"]
    assert v.lon == RUTA_CORTA[0]["lng"]

def test_vehicle_acumula_kilometros():
    v = Vehicle("EV-ACME-00001", RUTA_CORTA, sucursal="SUC-001")
    inicial = v.kilometros
    v.tick(60.0)
    assert v.kilometros > inicial

def test_vehicle_bateria_baja_con_distancia():
    v = Vehicle("EV-ACME-00001", RUTA_CORTA, sucursal="SUC-001")
    v.estado_carga = 50.0
    v.kilometros = 0
    # Forzar avance de 100km virtuales
    v.kilometros = 100
    v._actualizar_bateria(100.0)
    assert v.estado_carga < 50.0

def test_vehicle_bateria_no_baja_de_minimo():
    v = Vehicle("EV-ACME-00001", RUTA_CORTA, sucursal="SUC-001")
    v.estado_carga = 5.0
    v._actualizar_bateria(1000.0)
    assert v.estado_carga >= 5.0

def test_vehicle_offline_acumula_buffer():
    v = Vehicle("EV-ACME-00001", RUTA_CORTA, sucursal="SUC-001")
    v.offline = True
    v.offline_since = "2026-06-09T23:00:00Z"
    gps = v.generar_gps()
    v.buffer.append(gps)
    assert len(v.buffer) == 1

def test_vehicle_reconexion_limpia_buffer():
    v = Vehicle("EV-ACME-00001", RUTA_CORTA, sucursal="SUC-001")
    v.offline = True
    v.offline_since = "2026-06-09T23:00:00Z"
    v.buffer = [v.generar_gps(), v.generar_estado()]
    tramas = v.reconectar()
    assert v.offline is False
    assert v.buffer == []
    assert len(tramas) == 2
    assert tramas[-1]["reconexion"] is True

def test_vehicle_reconexion_marca_ultimo_estado_aunque_termine_en_gps():
    # Los campos de reconexión solo existen en el schema ESTADO —
    # si el buffer termina en GPS, se marca el ESTADO previo
    v = Vehicle("EV-ACME-00001", RUTA_CORTA, sucursal="SUC-001")
    v.offline = True
    v.offline_since = "2026-06-09T23:00:00Z"
    v.buffer = [v.generar_estado(), v.generar_gps()]
    tramas = v.reconectar()
    assert tramas[0]["reconexion"] is True
    assert tramas[0]["tramas_buffereadas"] == 2
    assert "reconexion" not in tramas[1]
