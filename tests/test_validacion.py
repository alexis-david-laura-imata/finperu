"""Validación del motor contra los casos resueltos del curso.

Corre con:  python -m pytest -q tests
Los archivos de Damodaran y del Tesoro se toman de plantillas/_fuente_curso (copias del curso),
así la prueba no depende de internet salvo para el espejo de la SMV (GitHub).
"""
from pathlib import Path

import pytest

from motor import config
from publicos import ruta
from motor.datos import damodaran, smv, tesoro
from motor.metodologia import LineaDeuda, calcular, kd_desde_tabla, recolectar

CURSO = config.FUENTE_CURSO
LAIVE = "CI0011"


def _curso(nombre: str) -> Path:
    p = ruta(nombre)
    if not p.exists():
        pytest.skip(f"Falta {p} (copia del curso)")
    return p


# ---- Fuentes individuales -------------------------------------------------------------
def test_rf_tesoro_ultimo_dia_habil():
    csv = _curso("par-yield-curve-rates-2020-2023.csv")
    assert tesoro.rf_10y(2023, csv).valor == pytest.approx(0.0388)   # práctica Laive 2023
    assert tesoro.rf_10y(2020, csv).valor == pytest.approx(0.0093)   # modelo docente 2020
    assert tesoro.rf_10y(2021, csv).valor == pytest.approx(0.0152)   # modelo docente 2021


def test_beta_damodaran_archivos_del_curso():
    b23 = damodaran.beta_desapalancada("Food Processing", 2023, local=_curso("betaemerg23.xls"))
    assert b23.valor == pytest.approx(0.6142, abs=1e-4)              # práctica usó 0.61
    b20 = damodaran.beta_desapalancada("Food Processing", 2021, local=_curso("betaemerg20.xls"))
    assert b20.valor == pytest.approx(0.7428, abs=1e-4)              # modelo 2021 usó 0.74
    assert "2024-01-05" in b23.detalle                                # fecha real del archivo


def test_prima_mercado_histretsp():
    h = _curso("histretSP.xls")
    # El modelo del docente pegó los datos con 4 decimales: tolerancia de 5 pb
    assert damodaran.prima_mercado(2019, local=h).valor == pytest.approx(0.064264, abs=5e-4)
    assert damodaran.prima_mercado(2020, local=h).valor == pytest.approx(0.064292, abs=5e-4)


def test_kd_tabla_laive_2023():
    lineas = [
        LineaDeuda("SOBREGIROS", "Banco de Crédito del Perú", 0.0815, 0.0876, 25935, 0, "S/ y US$"),
        LineaDeuda("SOBREGIROS", "Scotiabank Perú", 0.0785, None, 51706, 0),
        LineaDeuda("PRESTAMOS BANCARIOS", "Banco de Crédito del Perú", 0.0355, 0.0555, 11027, 15805),
        LineaDeuda("PRESTAMOS BANCARIOS", "BBVA Continental", 0.0525, None, 3700, 5505),
    ]
    k = kd_desde_tabla(lineas)
    assert k["kd"] == pytest.approx(0.069986, abs=1e-6)
    assert k["total_deuda_nota"] == 113678


# ---- SMV (espejo GitHub) --------------------------------------------------------------
def test_smv_laive_2023_cuadra_con_pdf_auditado():
    df, f, tipo = smv.estados(LAIVE, 2023, via="espejo")
    c, c0 = smv.conceptos(df), smv.conceptos(df, comparativo=True)
    assert tipo == "I"                                   # Laive solo reporta individual
    assert c["otros_pasivos_financieros_cp"] == 92368    # PDF nota 12
    assert c["otros_pasivos_financieros_lp"] == 21310
    assert c["patrimonio_total"] == 232342
    assert c["utilidad_operativa"] == 52286
    assert c0["patrimonio_total"] == 214226              # comparativo 2022
    assert c["activo_total"] == 538716


# ---- Modelo completo --------------------------------------------------------------------
def test_wacc_eva_laive_2023_igual_a_la_practica():
    """Mismos insumos que la práctica calificada -> mismos resultados."""
    lineas = [
        LineaDeuda("SOBREGIROS", "Banco de Crédito del Perú", 0.0815, 0.0876, 25935, 0, "S/ y US$"),
        LineaDeuda("SOBREGIROS", "Scotiabank Perú", 0.0785, None, 51706, 0),
        LineaDeuda("PRESTAMOS BANCARIOS", "Banco de Crédito del Perú", 0.0355, 0.0555, 11027, 15805),
        LineaDeuda("PRESTAMOS BANCARIOS", "BBVA Continental", 0.0525, None, 3700, 5505),
    ]
    ins = recolectar(LAIVE, 2023, "Food Processing", kd=lineas, via_smv="espejo",
                     sobrescribir={"inflacion_pe": 0.0341, "inflacion_us": 0.034, "riesgo_pais": 0.0162,
                                   "prima": 0.06799170755600067, "beta_u": 0.61},
                     locales={"tesoro": _curso("par-yield-curve-rates-2020-2023.csv")})
    r = calcular(ins)
    assert r["ke"] == pytest.approx(0.110887, abs=1e-6)
    assert r["wacc"] == pytest.approx(0.090667, abs=1e-6)
    assert r["roic"] == pytest.approx(0.112153, abs=1e-6)
    assert r["eva"] == pytest.approx(7061.95, abs=0.5)
    assert all(c["ok"] for c in r["controles"])
    assert not [a for a in ins.avisos if "tabla de Kd" in a]   # la tabla Kd cuadra con el ESF
    assert any("individuales" in a for a in ins.avisos)        # Laive no presenta consolidados
