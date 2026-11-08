"""Empresas que no usan el plan de cuentas 'D' (bancos, aseguradoras, AFP, agentes de bolsa, CAVALI).

Caso que originó estas pruebas: BANCO BBVA PERU 2025 fallaba con
"unsupported operand type(s) for +: 'NoneType' and 'NoneType'" porque los bancos reportan a la SMV con el
plan 'F' (1F2704/1F3002 en vez de 1D0309/1D0401) y la deuda quedaba en None.

Los datos son un recorte real del servicio de la SMV (ejercicio 2025, vía espejo smv-eeff): tests/fixtures/smv_planes_2025.csv
"""
import shutil

import pandas as pd
import pytest
from openpyxl import load_workbook

from motor import errores
from motor.datos import smv
from motor.datos.red import fuente_local
from motor.metodologia import DatosIncompletos, calcular, recolectar
from publicos import FIXTURES

CSV = FIXTURES / "smv_planes_2025.csv"
MERCADO = {"rf": 0.0418, "riesgo_pais": 0.0127, "prima": 0.070323, "beta_u": 0.2703,
           "inflacion_pe": 0.0151, "inflacion_us": 0.027, "beta_l_industria": 0.5857}
REQUERIDOS = ["otros_pasivos_financieros_cp", "otros_pasivos_financieros_lp", "patrimonio_total",
              "utilidad_operativa", "activo_total", "pasivo_total", "utilidad_neta"]


def _estados_fixture(rpj, tipo):
    df = pd.read_csv(CSV, dtype={"rpj": str})
    sub = df[(df.rpj == rpj) & (df.tipo == tipo)].drop(columns=["rpj", "tipo"])
    assert len(sub), f"{rpj} {tipo} no está en el fixture"
    return smv._ordenar(sub)


@pytest.fixture
def smv_offline(monkeypatch):
    """smv.estados() responde con el fixture (consolidado si existe, si no individual), sin internet."""
    fuente = fuente_local(CSV, "smv", nota="Recorte SMV 2025 para pruebas")

    def estados(rpj, ejercicio, periodo="A", tipo="C", via="auto"):
        tipos = [tipo] + (["I"] if tipo == "C" else [])
        df = pd.read_csv(CSV, dtype={"rpj": str})
        for t in tipos:
            if ((df.rpj == rpj) & (df.tipo == t)).any():
                return _estados_fixture(rpj, t), fuente, t
        raise LookupError(f"Sin estados para RPJ {rpj}")

    monkeypatch.setattr(smv, "estados", estados)
    monkeypatch.setattr(smv, "buscar_empresa", lambda texto, limite=10: [{"rpj": texto, "nombre": f"Empresa {texto}"}])
    return estados


# ------------------------------------------------------------------ mapeo de cuentas por plan
@pytest.mark.parametrize("rpj,tipo,plan", [
    ("B80004", "C", "F"), ("B80004", "I", "F"), ("CF0004", "I", "F"),   # bancos
    ("A80069", "I", "E"), ("OE3191", "I", "E"),                          # aseguradoras
    ("AFP002", "I", "A"), ("B80128", "I", "I"), ("ICLV01", "I", "V"),     # AFP, agente de bolsa, CAVALI
    ("002766", "C", "D"),                                                # empresa general
])
def test_conceptos_en_todos_los_planes(rpj, tipo, plan):
    df = _estados_fixture(rpj, tipo)
    assert smv.plan_de_cuentas(df) == plan
    for comparativo in (False, True):
        c = smv.conceptos(df, comparativo)
        faltan = [k for k in REQUERIDOS if c.get(k) is None]
        assert not faltan, f"{rpj} {tipo}: faltan {faltan}"
        assert c["activo_total"] == pytest.approx(c["pasivo_total"] + c["patrimonio_total"], abs=2)
    assert smv.cuentas_concepto(df, "otros_pasivos_financieros_cp") or smv.cuentas_concepto(df, "otros_pasivos_financieros_lp")


def test_bbva_consolidado_cuentas_exactas():
    df = _estados_fixture("B80004", "C")
    c = smv.conceptos(df)
    # Igual al ESF del PDF auditado: "Adeudos y obligaciones financieras 7,917,530"
    assert smv.cuentas_concepto(df, "otros_pasivos_financieros_cp") == ["1F2704"]
    assert smv.cuentas_concepto(df, "otros_pasivos_financieros_lp") == ["1F3002"]
    assert c["otros_pasivos_financieros_cp"] + c["otros_pasivos_financieros_lp"] == 7_917_530
    assert c["patrimonio_total"] == 14_991_629
    assert c["utilidad_operativa"] == 3_291_004
    assert smv.conceptos(df, True)["otros_pasivos_financieros_cp"] == 106_003


def test_bbva_individual_no_duplica_deuda():
    df = _estados_fixture("B80004", "I")
    c = smv.conceptos(df)
    assert smv.cuentas_concepto(df, "otros_pasivos_financieros_cp") == ["1F2401"]
    assert smv.cuentas_concepto(df, "otros_pasivos_financieros_lp") == []
    assert c["otros_pasivos_financieros_cp"] == 7_869_656 and c["otros_pasivos_financieros_lp"] == 0
    assert c["intereses_deuda"] == -483_731


def test_descripcion_como_respaldo_en_plan_desconocido():
    df = _estados_fixture("002766", "C").copy()
    df["cuenta"] = df["cuenta"].str.replace("D", "Z", n=1, regex=False)     # plan inventado
    c = smv.conceptos(df)
    original = smv.conceptos(_estados_fixture("002766", "C"))
    assert c["patrimonio_total"] == original["patrimonio_total"]
    assert c["activo_total"] == original["activo_total"]


# ------------------------------------------------------------------ modelo completo
def test_bbva_2025_modelo_completo(smv_offline):
    ins = recolectar("B80004", 2025, "Bank (Money Center)", sobrescribir=MERCADO)
    assert ins.parametros["plan_cuentas"] == "F"
    assert any("sistema financiero" in a for a in ins.avisos)
    # Kd del banco: intereses de adeudos (individual) / adeudos promedio (individual)
    df_i = _estados_fixture("B80004", "I")
    d1 = smv.conceptos(df_i)["otros_pasivos_financieros_cp"]
    d0 = smv.conceptos(df_i, True)["otros_pasivos_financieros_cp"]
    assert ins.datos["kd"].valor == pytest.approx(483_731 / ((d1 + d0) / 2))
    assert 0.03 < ins.datos["kd"].valor < 0.10
    r = calcular(ins)
    assert r["D"] == 7_917_530 and r["E"] == 14_991_629
    # banco: beta apalancada de la industria (sin Hamada) y NOPAT con los intereses de adeudos sumados
    assert r["beta_l"] == 0.5857
    assert r["nopat"] == pytest.approx((3_291_004 + 483_731) * (1 - 0.295))
    # ROE = 16.9 %, igual al publicado por Apoyo & Asociados para BBVA Perú 2025
    assert r["roe"] == pytest.approx(2_390_911 / ((14_991_629 + 13_300_346) / 2))
    assert round(r["roe"], 3) == 0.169
    assert r["eva_accionista"] == pytest.approx((r["roe"] - r["ke"]) * r["patrimonio_promedio"])
    assert 0 < r["wacc"] < r["ke"]
    assert all(c["ok"] for c in r["controles"]), r["controles"]


@pytest.mark.parametrize("rpj", ["A80069", "AFP002", "B80128", "ICLV01", "002766"])
def test_modelo_otros_planes_no_falla(smv_offline, rpj):
    ins = recolectar(rpj, 2025, "Total Market", kd=0.07, sobrescribir=MERCADO)
    r = calcular(ins)
    assert r["wacc"] == r["wacc"] and r["roic"] == r["roic"]        # números, no NaN ni None


def test_excel_bbva(smv_offline, tmp_path):
    from motor.generar import generar_wacc
    s = generar_wacc("B80004", 2025, "Bank (Money Center)", kd=None, modo="archivo", velocidad=0,
                     sobrescribir=MERCADO)
    wb = load_workbook(s["excel"])
    nombres = wb.defined_names
    assert nombres["Deuda_CP"].attr_text.startswith("'EEFF'!")
    for n in ("Deuda_CP", "Deuda_LP", "Patrimonio", "Utilidad_Operativa", "WACC", "ROIC"):
        assert n in nombres, n
    if shutil.which("soffice") or shutil.which("libreoffice"):
        v = s["verificacion_excel"]
        assert v["estado"] == "OK"
        assert v["wacc"] == pytest.approx(s["resultados"]["wacc"], abs=1e-12)


# ------------------------------------------------------------------ errores claros
def test_datos_incompletos_mensaje_claro(smv_offline, monkeypatch):
    original = smv.estados

    def sin_patrimonio(*a, **k):
        df, f, t = original(*a, **k)
        return df[df.cuenta != "1F3306"].reset_index(drop=True), f, t

    monkeypatch.setattr(smv, "estados", sin_patrimonio)
    ins = recolectar("B80004", 2025, "Bank (Money Center)", kd=0.06, sobrescribir=MERCADO)
    with pytest.raises(DatosIncompletos) as e:
        calcular(ins)
    assert "total patrimonio" in str(e.value) and "NoneType" not in str(e.value)


def test_mensaje_libreria_faltante():
    try:
        import modulo_que_no_existe_finperu  # noqa: F401
    except ModuleNotFoundError as e:
        m = errores.mensaje(e)
    assert "modulo_que_no_existe_finperu" in m and "Instalar FinPeru.bat" in m
