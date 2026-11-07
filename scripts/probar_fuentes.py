"""Prueba en vivo de todas las fuentes (correr en Windows, con internet).

    python scripts/probar_fuentes.py

Para cada fuente imprime OK/FALLO, el valor obtenido y el valor esperado según el curso.
"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor import eventos  # noqa: E402
from motor.datos import bcrp, damodaran, smv, tesoro  # noqa: E402

eventos.SILENCIO = True
resultados = []


def probar(nombre, fn, esperado=None):
    try:
        v = fn()
        val = getattr(v, "valor", v)
        ok = esperado is None or (isinstance(val, (int, float)) and abs(val - esperado) < 5e-4)
        print(f"{'OK   ' if ok else 'DIFIERE'} {nombre:<45} {val!s:<22} esperado {esperado}")
        if hasattr(v, "detalle"):
            print(f"        {v.detalle}")
        resultados.append(ok)
    except Exception as e:  # noqa: BLE001
        print(f"FALLO {nombre:<45} {type(e).__name__}: {e}")
        traceback.print_exc(limit=1)
        resultados.append(False)


print("=" * 100)
print("FUENTES EN VIVO — FinPerú MCP")
print("=" * 100)
probar("Tesoro: Rf 10 años 2023", lambda: tesoro.rf_10y(2023), 0.0388)
probar("Tesoro: Rf 10 años 2025", lambda: tesoro.rf_10y(2025))
probar("BCRP: riesgo país dic-2023 (PN01129XM)", lambda: bcrp.riesgo_pais(2023), 0.0162)
probar("BCRP: riesgo país dic-2021", lambda: bcrp.riesgo_pais(2021), 0.0174)
probar("BCRP: inflación Perú 2023 (PN01273PM)", lambda: bcrp.inflacion_peru(2023), 0.0324)
probar("Damodaran: beta Food Processing FY2023", lambda: damodaran.beta_desapalancada("Food Processing", 2023), 0.6142)
probar("Damodaran: beta Food Processing actual", lambda: damodaran.beta_desapalancada("Food Processing", 2025))
probar("Damodaran: prima mercado 1928-2023", lambda: damodaran.prima_mercado(2023), 0.06799)
probar("SMV en vivo: buscar 'Laive'", lambda: smv.buscar_empresa("Laive")[0]["rpj"])
probar("SMV en vivo (SOAP): patrimonio Laive 2023",
       lambda: smv.conceptos(smv.estados("CI0011", 2023, via="smv")[0])["patrimonio_total"], 232342)
probar("SMV espejo: patrimonio Laive 2023",
       lambda: smv.conceptos(smv.estados("CI0011", 2023, via="espejo")[0])["patrimonio_total"], 232342)
print("=" * 100)
print(f"{sum(resultados)}/{len(resultados)} fuentes OK")
