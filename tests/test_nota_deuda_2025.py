"""Notas de deuda reales 2025 (texto extraído de los PDF auditados publicados por la SMV).

- BBVA Perú (nota 13 'Adeudos y obligaciones financieras'): saldo total por año, tasas en sub-notas,
  préstamos a 'SOFR + margen' y bonos con la tasa en la redacción.
- Backus (nota 15 'Obligaciones financieras'): arrendamientos con tasa por banco y 'otros arrendamientos' sin tasa.
Antes de la v0.2.2 el lector no encontraba ninguna de las dos y el Kd caía al aproximado (13.37% en Backus).
"""
import pytest

from motor.datos.nota_deuda import _buscar_nota, extraer_de_lineas, resolver_variables
from motor.generar import lineas_kd
from motor.metodologia import kd_desde_tabla
from publicos import FIXTURES

SOFR_2025 = 0.0387          # NY Fed, 31/12/2025


def _leer(nombre, deuda, sofr=SOFR_2025):
    textos = (FIXTURES / nombre).read_text(encoding="utf-8").split("\f")
    pag, tabla, completo = _buscar_nota(textos, sofr)
    return extraer_de_lineas(tabla, completo, pag, deuda_esf=deuda, anio=2025, tasa_respaldo=None)


def test_sofr_mas_margen():
    assert resolver_variables("China Development Bank 180,000 605,340 SOFR + 1.37%", 0.0387).endswith("5.24%")
    assert resolver_variables("SOFR + 1.35%", None) == "SOFR + 1.35%"


def test_bbva_nota_13():
    r = _leer("nota_deuda_bbva_2025.txt", 7_917_530)
    assert r.encontrada and r.cuadra and r.total_extraido == 7_917_530
    por = {l["entidad"][:22]: l for l in r.lineas}
    # (a) y (b): promedio ponderado por saldo de cada préstamo (verificado a mano)
    assert por["Instituciones financie"]["tasa_min"] == pytest.approx(0.042698, abs=1e-6)
    assert por["Organismos financieros"]["tasa_min"] == pytest.approx(0.050861, abs=1e-6)
    assert por["Fondo Mivivienda - Sis"]["tasa_min"] == 0.0625
    assert (por["Corporación Financiera"]["tasa_min"], por["Corporación Financiera"]["tasa_max"]) == (0.0595, 0.0728)
    assert (por["Bonos subordinados"]["tasa_min"], por["Bonos subordinados"]["tasa_max"]) == (0.062, 0.065)
    assert por["Certificados de depósi"]["tasa_min"] == 0.0438
    assert {l["tipo"] for l in r.lineas} == {"ADEUDOS", "VALORES Y TITULOS", "INTERESES DEVENGADOS"}
    kd = kd_desde_tabla(lineas_kd(r.lineas))["kd"]
    assert kd == pytest.approx(0.055854, abs=1e-6)


def test_backus_nota_15():
    r = _leer("nota_deuda_backus_2025.txt", 165_206)
    assert r.cuadra and len(r.lineas) == 4
    assert [l["tasa_min"] for l in r.lineas[:3]] == [0.066, 0.074, 0.0645]
    otros = r.lineas[3]
    assert otros["tipo"] == "OTROS ARRENDAMIENTOS" and "NO REVELADA" in otros["nota"]
    assert otros["tasa_min"] == pytest.approx(0.068506, abs=1e-6)     # promedio de los arrendamientos de la nota
    assert kd_desde_tabla(lineas_kd(r.lineas))["kd"] == pytest.approx(0.068506, abs=1e-6)


def test_sin_sofr_la_fila_no_inventa_tasa():
    r = _leer("nota_deuda_bbva_2025.txt", 7_917_530, sofr=None)
    inst = next(l for l in r.lineas if l["entidad"].startswith("Instituciones"))
    assert inst["tasa_min"] >= 0.03            # el margen "SOFR + 1.37%" nunca se toma como si fuera la tasa
