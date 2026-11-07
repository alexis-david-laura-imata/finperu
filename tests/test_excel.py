"""El Excel generado debe calcular lo mismo que Python (sin abrir Excel).

Usa LienzoArchivo (openpyxl). Si hay LibreOffice, además recalcula el archivo y compara.
"""
import shutil

import pytest
from openpyxl import load_workbook

from motor import config
from publicos import ruta
from motor.generar import generar_wacc

KD = [dict(tipo="SOBREGIROS", entidad="BCP", tasa_min=0.0815, tasa_max=0.0876, corriente=25935),
      dict(tipo="SOBREGIROS", entidad="Scotiabank", tasa_min=0.0785, corriente=51706),
      dict(tipo="PRESTAMOS BANCARIOS", entidad="BCP", tasa_min=0.0355, tasa_max=0.0555, corriente=11027,
           no_corriente=15805),
      dict(tipo="PRESTAMOS BANCARIOS", entidad="BBVA", tasa_min=0.0525, corriente=3700, no_corriente=5505)]


def test_modelo_laive_2023_archivo(tmp_path):
    csv = ruta("par-yield-curve-rates-2020-2023.csv")
    if not csv.exists():
        pytest.skip("falta CSV del curso")
    s = generar_wacc("CI0011", 2023, "Food Processing", kd=KD, via_smv="espejo", modo="archivo",
                     sobrescribir={"inflacion_pe": 0.0341, "inflacion_us": 0.034, "riesgo_pais": 0.0162,
                                   "prima": 0.06799170755600067, "beta_u": 0.61},
                     locales={"tesoro": csv})
    wb = load_workbook(s["excel"])
    assert wb.sheetnames == ["Portada", "Parametros", "EEFF", "Kd", "Mercado", "CPPC", "EVA", "Controles",
                             "Fuentes", "Registro"]
    for nombre in ("WACC", "Ke_Final", "ROIC", "Valor_EVA", "Tasa_Rf", "Beta_L", "Kd_Prom", "Estado_Controles"):
        assert nombre in wb.defined_names, nombre
    assert s["resultados"]["wacc"] == pytest.approx(0.090667, abs=1e-6)
    if shutil.which("soffice") or shutil.which("libreoffice"):
        v = s["verificacion_excel"]
        assert v["wacc"] == pytest.approx(s["resultados"]["wacc"], abs=1e-12)
        assert v["eva"] == pytest.approx(s["resultados"]["eva"], abs=1e-6)
        assert v["estado"] == "OK"
