"""Escala la flota: python escalar_flota.py 300"""
import os
import sys
import json
from dotenv import load_dotenv
from generator.catalog import cargar_catalogo, extender_catalogo
from generator.routes import cargar_o_generar_rutas

load_dotenv()

def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python escalar_flota.py <n_total>")
    n_total = int(sys.argv[1])

    catalogo = cargar_catalogo("catalog.json")
    print(f"Flota actual: {len(catalogo['vehiculos'])} vehículos → objetivo: {n_total}")
    catalogo = extender_catalogo(catalogo, n_total)
    with open("catalog.json", "w", encoding="utf-8") as f:
        json.dump(catalogo, f, ensure_ascii=False, indent=2)

    rutas = cargar_o_generar_rutas("routes.json", catalogo, os.getenv("GOOGLE_MAPS_API_KEY"))
    print(f"\nListo: {len(catalogo['vehiculos'])} vehículos, {len(rutas)} rutas")
    print("Pendiente: copiar catalog.json y routes.json a frontend/ y correr export_catalog.py")

if __name__ == "__main__":
    main()
