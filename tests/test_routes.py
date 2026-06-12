import pytest
from unittest.mock import patch, MagicMock
from generator.routes import _punto_aleatorio_en_bbox, _parsear_ruta, cargar_o_generar_rutas

BBOX = {"lat_min": 14.55, "lat_max": 14.75, "lon_min": -90.65, "lon_max": -90.45}

RESPUESTA_MAPS_MOCK = {
    "routes": [{
        "legs": [{
            "steps": [
                {"polyline": {"encodedPolyline": "urqnCdjkrP?eA"}},
                {"polyline": {"encodedPolyline": "wuqnCdjkrP_A?"}},
            ]
        }]
    }]
}

def test_punto_aleatorio_en_bbox():
    for _ in range(20):
        lat, lon = _punto_aleatorio_en_bbox(BBOX)
        assert BBOX["lat_min"] <= lat <= BBOX["lat_max"]
        assert BBOX["lon_min"] <= lon <= BBOX["lon_max"]

def test_parsear_ruta_retorna_lista_de_puntos():
    puntos = _parsear_ruta(RESPUESTA_MAPS_MOCK)
    assert isinstance(puntos, list)
    assert len(puntos) >= 2
    assert all("lat" in p and "lng" in p for p in puntos)

def test_parsear_ruta_respuesta_vacia_lanza_error():
    with pytest.raises(ValueError):
        _parsear_ruta({"routes": []})

def test_cargar_rutas_existentes(tmp_path):
    import json
    ruta_mock = {"EV-ACME-00001": [{"lat": 14.60, "lng": -90.51}]}
    f = tmp_path / "routes.json"
    f.write_text(json.dumps(ruta_mock))
    rutas = cargar_o_generar_rutas(str(f), catalogo=None, api_key=None)
    assert "EV-ACME-00001" in rutas
