import math
from generator.physics import haversine_km, bearing_deg, delta_bearing, speed_kmh

def test_haversine_misma_posicion():
    assert haversine_km(14.6012, -90.5189, 14.6012, -90.5189) == 0.0

def test_haversine_distancia_conocida():
    # Guatemala a ~1km al norte
    d = haversine_km(14.6012, -90.5189, 14.6102, -90.5189)
    assert 0.9 < d < 1.1

def test_bearing_norte():
    b = bearing_deg(14.60, -90.52, 14.61, -90.52)
    assert 355 < b or b < 5  # ~0 grados = norte

def test_bearing_este():
    b = bearing_deg(14.60, -90.52, 14.60, -90.51)
    assert 85 < b < 95  # ~90 grados = este

def test_delta_bearing_recta():
    # Misma dirección → delta pequeño
    d = delta_bearing(10.0, 12.0)
    assert d == 2.0

def test_delta_bearing_curva_cerrada():
    # Giro de 90 grados
    d = delta_bearing(10.0, 100.0)
    assert d == 90.0

def test_delta_bearing_wrap_around():
    # De 355 a 5 grados = 10 grados, no 350
    d = delta_bearing(355.0, 5.0)
    assert d == 10.0

def test_speed_curva():
    v = speed_kmh(delta=30.0)
    assert 15 <= v <= 25

def test_speed_recta():
    v = speed_kmh(delta=5.0)
    assert 35 <= v <= 55
