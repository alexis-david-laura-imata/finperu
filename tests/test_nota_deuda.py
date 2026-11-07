"""Lector de la nota de deuda: tres formatos reales distintos."""
import pytest

from motor import config
from publicos import ruta
from motor.datos.nota_deuda import _buscar_nota, extraer, extraer_de_lineas

LAIVE = ruta("19379e9c-920a-4147-bde0-ae4d56869b84.pdf")      # Laive EEFF 2023 (auditado)
NESSUS = ruta("NOJ404512022TI101 (1).PDF")                      # Casa Andina 1T-2022


def _pdf(p):
    if not p.exists():
        pytest.skip(f"falta {p.name}")
    return p


def test_laive_2023_igual_a_la_nota_12():
    r = extraer(_pdf(LAIVE), deuda_esf=113678, anio=2023)
    assert r.pagina == 38 and r.cuadra and r.total_extraido == 113678
    bcp = r.lineas[0]
    assert (bcp["tipo"], bcp["tasa_min"], bcp["tasa_max"], bcp["corriente"]) == ("SOBREGIROS", 0.0815, 0.0875, 25935)
    assert [l["tipo"] for l in r.lineas] == ["SOBREGIROS", "SOBREGIROS", "PRESTAMOS BANCARIOS", "PRESTAMOS BANCARIOS"]


def test_laive_2022_segundo_bloque_y_fila_partida():
    r = extraer(_pdf(LAIVE), deuda_esf=97098, anio=2022)
    assert r.cuadra and r.bloque_usado == 1
    interbank = [l for l in r.lineas if "Internacional" in l["entidad"]][0]   # nombre partido en 2 líneas
    assert interbank["tasa_min"] == 0.0883 and interbank["corriente"] == 17008


def test_casa_andina_orden_distinto_de_columnas():
    r = extraer(_pdf(NESSUS), deuda_esf=207501)
    assert r.cuadra
    assert {l["tipo"] for l in r.lineas} == {"PRESTAMOS BANCARIOS", "ARRENDAMIENTO FINANCIERO", "BONOS"}
    assert r.lineas[1]["moneda"] == "US$" and r.lineas[1]["vencimiento"] == "2026"


def test_gloria_columnas_intercaladas_y_tasa_en_subnota():
    texto = """14. OBLIGACIONES FINANCIERAS
(a) Este rubro comprende las siguientes obligaciones financieras:
Corriente No corriente Total
2025 2024 2025 2024 2025 2024
S/000 S/000 S/000 S/000 S/000 S/000
Pagarés (b) 138,710 92,286 1,471,312 1,275,118 1,610,022 1,367,404
Bonos (c) - - 150,000 150,000 150,000 150,000
138,710 92,286 1,621,312 1,425,118 1,760,022 1,517,404
(b) Al 31 de diciembre de 2025 y 2024, los saldos por pagarés bancarios se detallan como siguen:
Banco de Crédito del Perú S. A. (i) Soles 1 1 447,615 410,000
(c) A continuación, se presenta la composición de los programas de emisión de bonos corporativos al 31
emisión 150,000 5/02/2015 5/02/2035 7.13 Semestral partir del 05.08.2032 150,000 150,000
15. CUENTAS POR PAGAR COMERCIALES"""
    pag, tabla, completo = _buscar_nota([texto])
    r = extraer_de_lineas(tabla, completo, pag, deuda_esf=1760022, anio=2025, tasa_respaldo=0.06)
    assert r.cuadra
    pag_, bono = r.lineas
    assert (pag_["corriente"], pag_["no_corriente"]) == (138710, 1471312)
    assert pag_["tasa_min"] == 0.06 and "NO REVELADA" in pag_["nota"]
    assert bono["tasa_min"] == 0.0713 and bono["tipo"] == "BONOS"
