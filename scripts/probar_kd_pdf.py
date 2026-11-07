"""Prueba en vivo del lector de la nota de deuda con varias empresas (correr en Windows).

    python scripts\\probar_kd_pdf.py                  # lista por defecto, navegador oculto
    python scripts\\probar_kd_pdf.py --visible        # para ver el recorrido en la SMV
    python scripts\\probar_kd_pdf.py "Alicorp" 2024   # una empresa
"""
import argparse
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor import eventos  # noqa: E402
from motor.datos import smv  # noqa: E402
from motor.generar import kd_desde_pdf  # noqa: E402

eventos.SILENCIO = True
CASOS = [("Laive", 2023), ("Leche Gloria", 2025), ("Alicorp", 2024), ("Backus", 2024), ("Ferreycorp", 2024),
         ("UNACEM", 2024), ("Cementos Pacasmayo", 2024), ("Engie Energia", 2024)]

ap = argparse.ArgumentParser()
ap.add_argument("empresa", nargs="?")
ap.add_argument("anio", nargs="?", type=int)
ap.add_argument("--visible", action="store_true")
a = ap.parse_args()
casos = [(a.empresa, a.anio)] if a.empresa else CASOS

resumen = []
for nombre, anio in casos:
    e = smv.buscar_empresa(nombre)[0]
    print("=" * 100)
    print(f"{e['nombre']} ({e['rpj']}) {anio}")
    try:
        r = kd_desde_pdf(e["rpj"], anio, visible=a.visible)
        sin_tasa = sum(1 for l in r["lineas"] if "NO REVELADA" in l["nota"])
        print(f"  pág. {r['pagina']} · {len(r['lineas'])} líneas · total {r['total_extraido']} vs ESF {r['deuda_esf']} "
              f"· cuadra={r['cuadra']} · sin tasa={sin_tasa} · Kd={r.get('kd_estimado')}")
        for l in r["lineas"]:
            print(f"    {l['tipo']:<24} {l['entidad'][:38]:<38} {l['tasa_min']} {l['tasa_max']} "
                  f"{l['corriente']:>12,.0f} {l['no_corriente']:>12,.0f}")
        for av in r["avisos"]:
            print("   ⚠", av)
        resumen.append((e["nombre"][:30], anio, "CUADRA" if r["cuadra"] else "NO CUADRA", sin_tasa))
    except Exception as ex:  # noqa: BLE001
        print("  FALLO:", ex)
        traceback.print_exc(limit=2)
        resumen.append((e["nombre"][:30], anio, "FALLO", "-"))
print("=" * 100)
for x in resumen:
    print(f"{x[0]:<32} {x[1]}  {x[2]:<10} filas sin tasa: {x[3]}")
