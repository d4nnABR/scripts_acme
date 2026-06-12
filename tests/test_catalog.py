import os, json, tempfile, pytest
from generator.catalog import generar_catalogo, cargar_catalogo

# Los tests no llaman a la red: usar_api=False fuerza el fallback local

def test_genera_100_vehiculos():
    cat = generar_catalogo(usar_api=False)
    assert len(cat["vehiculos"]) == 100

def test_clientes_nombres_unicos():
    # Cada cliente es una persona distinta — sin "José Rodríguez" repetido
    cat = generar_catalogo(usar_api=False)
    nombres = [c["nombre_cliente"] for c in cat["clientes"]]
    assert len(set(nombres)) == 100

def test_clientes_correos_unicos():
    cat = generar_catalogo(usar_api=False)
    correos = [c["correo"] for c in cat["clientes"]]
    assert len(set(correos)) == 100

def test_genera_10_sucursales():
    cat = generar_catalogo(usar_api=False)
    assert len(cat["sucursales"]) == 10

def test_genera_100_clientes():
    cat = generar_catalogo(usar_api=False)
    assert len(cat["clientes"]) == 100

def test_genera_100_asignaciones():
    cat = generar_catalogo(usar_api=False)
    assert len(cat["cliente_vehiculo"]) == 100

def test_vehiculo_tiene_campos_requeridos():
    cat = generar_catalogo(usar_api=False)
    v = cat["vehiculos"][0]
    assert all(k in v for k in ["id_vehiculo", "modelo", "anio", "id_sucursal"])

def test_sucursal_tiene_bounding_box():
    cat = generar_catalogo(usar_api=False)
    s = cat["sucursales"][0]
    assert all(k in s for k in ["id_sucursal", "nombre_sucursal", "pais", "ciudad", "bbox"])
    assert all(k in s["bbox"] for k in ["lat_min", "lat_max", "lon_min", "lon_max"])

def test_vehiculos_distribuidos_por_sucursal():
    cat = generar_catalogo(usar_api=False)
    v = cat["vehiculos"]
    assert v[0]["id_sucursal"] == "SUC-001"
    assert v[10]["id_sucursal"] == "SUC-002"
    assert v[90]["id_sucursal"] == "SUC-010"

def test_guarda_y_carga_json():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        cat = generar_catalogo(usar_api=False)
        with open(path, "w") as f:
            json.dump(cat, f)
        loaded = cargar_catalogo(path)
        assert len(loaded["vehiculos"]) == 100
    finally:
        os.unlink(path)
