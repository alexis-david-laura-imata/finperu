"""Estados financieros de la SMV (Superintendencia del Mercado de Valores del Perú).

Dos vías, en este orden:
1. EN VIVO: servicio de datos abiertos SOAP de la SMV (mvnet.smv.gob.pe). Devuelve TODAS las
   empresas de un periodo; se cachea y se filtra por RPJ.
2. ESPEJO: base abierta smv-eeff (AtlasLedger, GitHub), que replica ese mismo servicio y se
   actualiza cada mes. Se usa si la SMV no responde.
   Atribución requerida (ODbL): datos de la SMV; base derivada smv-eeff.

La SMV usa un plan de cuentas distinto según el tipo de empresa (2.º carácter del código):
  D  empresas en general (la metodología del curso):  1D0309 + 1D0401 otros pasivos financieros,
     1D07ST patrimonio, 2D03ST ganancia operativa
  F  bancos, financieras y cajas (p.ej. BBVA, BCP): 1F2704 + 1F3002 adeudos y obligaciones financieras,
     1F3306 patrimonio, 2F2801 resultado de operación
  E  aseguradoras · A  AFP · I  agentes de intermediación · V  instituciones de compensación/bolsa
Si una cuenta no está en el mapa del plan, se busca por su descripción.
"""
from __future__ import annotations

import io
import json
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

from .. import config
from ..eventos import emitir
from .red import Dato, Fuente, descargar

SOAP_URL = "https://mvnet.smv.gob.pe/ws_od_eeff/WebServiceInfoFinanciera.asmx"
NS_TEMPURI = "http://tempuri.org/"
OPERACIONES = {"BG": "obtener_BalanceGeneral", "ER": "obtener_GanciaPerdida",
               "FE": "obtener_FlujoEfectivo", "ORI": "obtener_ResultadosIntegrales"}

ESPEJO = "https://raw.githubusercontent.com/AtlasLedger/smv-eeff/main/data"
CARPETA = config.CACHE / "smv"

# Conceptos clave -> cuentas SMV que lo componen, por plan de cuentas.
# Una lista de códigos se suma; una lista de listas son alternativas (se usa la primera presente).
CONCEPTOS_D = {
    "efectivo": ["1D0109"],
    "activo_corriente": ["1D01ST"],
    "activo_total": ["1D020T"],
    "otros_pasivos_financieros_cp": ["1D0309"],
    "pasivo_corriente": ["1D03ST"],
    "otros_pasivos_financieros_lp": ["1D0401"],
    "pasivo_total": ["1D040T"],
    "patrimonio_total": ["1D07ST"],
    "pasivo_y_patrimonio": ["1D070T"],
    "ingresos": ["2D01ST"],
    "costo_ventas": ["2D0201"],
    "utilidad_bruta": ["2D02ST"],
    "utilidad_operativa": ["2D03ST"],
    "gastos_financieros": ["2D0402"],
    "utilidad_antes_impuestos": ["2D04ST"],
    "impuesto_renta": ["2D0502"],
    "utilidad_neta": ["2D07ST"],
}
CONCEPTOS_F = {   # sistema financiero: los depósitos del público son pasivo operativo, no deuda financiera
    "efectivo": ["1F0101"],
    "activo_corriente": ["1F01ST"],
    "activo_total": ["1F2001"],
    # adeudos y obligaciones financieras: el consolidado separa corriente/no corriente; el individual trae
    # un solo total (1F2401), que se toma como corriente para no duplicar.
    "otros_pasivos_financieros_cp": [["1F2704"], ["1F2401"]],
    "pasivo_corriente": ["1F2902"],
    "otros_pasivos_financieros_lp": [["1F3002"]],
    "pasivo_total": ["1F3101"],
    "patrimonio_total": ["1F3306"],
    "pasivo_y_patrimonio": ["1F3307"],
    "ingresos": [["2F01ST"], ["2F0101"]],                # alternativas: consolidado / individual
    "costo_ventas": [["2F03ST"], ["2F0301"]],
    "utilidad_bruta": ["2F2301"],
    "utilidad_operativa": ["2F2801"],                    # resultado de operación
    "gastos_financieros": ["2F0301"],                    # gastos por intereses (costo de fondeo)
    "utilidad_antes_impuestos": [["2F2809"], ["2F1302"]],
    "impuesto_renta": ["2F1403"],
    "utilidad_neta": ["2F1901"],
    # pasivos que pagan intereses (para el Kd aproximado = costo de fondeo)
    "pasivos_con_costo": [["1F2101", "1F2301", "1F2703", "1F2704", "1F3002"], ["1F2101", "1F2301", "1F2401"]],
    # intereses pagados por los adeudos y obligaciones (solo en el estado individual)
    "intereses_deuda": [["2F0404"]],
}
CONCEPTOS_E = {   # aseguradoras
    "efectivo": ["1E0101"], "activo_corriente": ["1E01ST"], "activo_total": ["1E02ST"],
    "otros_pasivos_financieros_cp": ["1E0310"], "pasivo_corriente": ["1E0309"],
    "otros_pasivos_financieros_lp": ["1E0401"], "pasivo_total": ["1E0501"], "patrimonio_total": ["1E0901"],
    "pasivo_y_patrimonio": ["1E1001"], "ingresos": ["2E0201"], "utilidad_operativa": [["2E1501"], ["2E1508"]],
    "gastos_financieros": ["2E1202"], "utilidad_antes_impuestos": ["2E1509"], "impuesto_renta": ["2E1602"],
    "utilidad_neta": ["2E2101"],
}
CONCEPTOS_A = {   # AFP
    "efectivo": ["1A0109"], "activo_corriente": ["1A01ST"], "activo_total": ["1A020T"],
    "otros_pasivos_financieros_cp": ["1A0306"], "pasivo_corriente": ["1A03ST"],
    "otros_pasivos_financieros_lp": [], "pasivo_total": ["1A040T"], "patrimonio_total": ["1A07ST"],
    "pasivo_y_patrimonio": ["1A070T"], "ingresos": ["2A01ST"], "utilidad_operativa": ["2A03ST"],
    "gastos_financieros": ["2A0402"], "utilidad_antes_impuestos": ["2A08ST"], "impuesto_renta": ["2A0502"],
    "utilidad_neta": ["2A07ST"],
}
CONCEPTOS_I = {   # sociedades agentes de bolsa / intermediación
    "activo_corriente": ["1I1071"], "activo_total": ["1I1131"], "otros_pasivos_financieros_cp": ["1I1431"],
    "pasivo_corriente": ["1I1461"], "otros_pasivos_financieros_lp": ["1I1470"], "pasivo_total": ["1I1491"],
    "patrimonio_total": ["1I1551"], "pasivo_y_patrimonio": ["1I1552"], "ingresos": ["2I2031"],
    "utilidad_operativa": ["2I2071"], "gastos_financieros": ["2I2090"], "utilidad_antes_impuestos": ["2I2121"],
    "impuesto_renta": ["2I2140"], "utilidad_neta": ["2I2161"],
}
CONCEPTOS_V = {   # instituciones de compensación y bolsa
    "activo_corriente": ["1V01ST"], "activo_total": ["1V020T"], "otros_pasivos_financieros_cp": ["1V0309"],
    "pasivo_corriente": ["1V03ST"], "otros_pasivos_financieros_lp": ["1V0401"], "pasivo_total": ["1V040T"],
    "patrimonio_total": ["1V07ST"], "pasivo_y_patrimonio": ["1V070T"], "ingresos": ["2V01ST"],
    "utilidad_operativa": ["2V03ST"], "gastos_financieros": ["2V0402"], "utilidad_antes_impuestos": ["2V04ST"],
    "impuesto_renta": ["2V0502"], "utilidad_neta": ["2V07ST"],
}
CONCEPTOS_POR_PLAN = {"D": CONCEPTOS_D, "F": CONCEPTOS_F, "E": CONCEPTOS_E, "A": CONCEPTOS_A,
                      "I": CONCEPTOS_I, "V": CONCEPTOS_V}
NOMBRE_PLAN = {"D": "empresas en general", "F": "sistema financiero (bancos, financieras, cajas)",
               "E": "empresas de seguros", "A": "AFP", "I": "agentes de intermediación",
               "V": "instituciones de compensación y bolsa"}
# Respaldo por descripción (plan desconocido o cuenta ausente). Prefijo 1 = balance, 2 = resultados.
DESCRIPCIONES = {
    "efectivo": ("1", r"^(EFECTIVO Y EQUIVALENTES?|CAJA Y BANCOS|DISPONIBLES?)\b"),
    "activo_corriente": ("1", r"^TOTAL (DE )?ACTIVOS? CORRIENTES?$"),
    "activo_total": ("1", r"^TOTAL (DE |DEL )?ACTIVOS?$"),
    "otros_pasivos_financieros_cp": ("1", r"^(OTROS PASIVOS FINANCIEROS|OBLIGACIONES FINANCIERAS|ADEUDAD?OS Y OBLIGACIONES FINANCIERAS)"),
    "pasivo_corriente": ("1", r"^TOTAL (DE )?PASIVOS? CORRIENTES?$"),
    "otros_pasivos_financieros_lp": ("1", r"^(OTROS PASIVOS FINANCIEROS|OBLIGACIONES FINANCIERAS|ADEUDAD?OS Y OBLIGACIONES FINANCIERAS)"),
    "pasivo_total": ("1", r"^TOTAL (DE |DEL )?PASIVOS?$"),
    "patrimonio_total": ("1", r"^TOTAL (DE |DEL )?PATRIMONIO( NETO)?$"),
    "pasivo_y_patrimonio": ("1", r"^TOTAL (DE |DEL )?PASIVOS? Y PATRIMONIO"),
    "ingresos": ("2", r"^(TOTAL DE )?INGRESOS (DE ACTIVIDADES ORDINARIAS|BRUTOS|OPERACIONALES)"),
    "utilidad_operativa": ("2", r"^(GANANCIA|UTILIDAD|RESULTADO)( \(?PERDIDA\)?)? (OPERATIVA|DE OPERACION|POR ACTIVIDADES DE OPERACION)$"),
    "gastos_financieros": ("2", r"^GASTOS FINANCIEROS$"),
    "utilidad_antes_impuestos": ("2", r"^(RESULTADO|UTILIDAD|GANANCIA).*ANTES (DEL? )?IMPUESTO"),
    "impuesto_renta": ("2", r"^(GASTO POR )?IMPUESTO A LAS? (GANANCIAS|RENTA)"),
    "utilidad_neta": ("2", r"^(RESULTADO|UTILIDAD|GANANCIA)( \(?PERDIDA\)?)? NET[OA] DEL EJERCICIO$"),
}
# Si estos conceptos no existen, la deuda vale 0 (empresa sin deuda financiera) en lugar de fallar.
CONCEPTOS_OPCIONALES_CERO = {"otros_pasivos_financieros_cp", "otros_pasivos_financieros_lp", "gastos_financieros",
                             "intereses_deuda"}


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().upper()
    return " ".join(t.replace(".", " ").replace(",", " ").split())


# ---------------------------------------------------------------- catálogo de empresas
def catalogo() -> tuple[pd.DataFrame, Fuente]:
    f = descargar(f"{ESPEJO}/csv/empresas.csv", CARPETA / "empresas.csv", "smv",
                  max_edad_horas=24 * 30, nota="Catálogo RPJ/RUC (smv-eeff, derivado de SMV, ODbL)")
    df = pd.read_csv(f.archivo, dtype=str, encoding="utf-8-sig").fillna("")
    df["rpj"] = df["rpj"].str.strip()
    return df, f


def buscar_empresa(texto: str, limite: int = 10) -> list[dict]:
    """Busca por nombre, RUC o RPJ. Prioriza emisoras con datos recientes."""
    df, _ = catalogo()
    q = _norm(texto)
    nombres = df["nombre"].map(_norm)
    m = (nombres.str.contains(q, regex=False) | (df["ruc"] == texto.strip()) |
         (df["rpj"].str.upper() == texto.strip().upper()))
    r = df[m].copy()
    r["_rank"] = (r["ultimo_periodo"].str[:4].replace("", "0").astype(int) * 10
                  + (r["tipo_empresa"] == "EMPRESAS EMISORAS").astype(int) * 5
                  + (nombres[m] == q).astype(int) * 100)
    r = r.sort_values("_rank", ascending=False).head(limite)
    return r.drop(columns="_rank").to_dict("records")


def cuentas() -> pd.DataFrame:
    f = descargar(f"{ESPEJO}/cuentas.parquet", CARPETA / "cuentas.parquet", "smv", max_edad_horas=24 * 30)
    return pd.read_parquet(f.archivo)[["cuenta", "estado", "plan", "descripcion", "orden"]]


# ---------------------------------------------------------------- vía 1: SOAP en vivo
def _sobre(operacion: str, ejercicio: int, periodo: str, tipo: str) -> bytes:
    return (f'<?xml version="1.0" encoding="utf-8"?><soap:Envelope '
            f'xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
            f'<{operacion} xmlns="{NS_TEMPURI}"><Ejercicio>{ejercicio}</Ejercicio>'
            f'<Periodo>{periodo}</Periodo><Tipo>{tipo}</Tipo></{operacion}></soap:Body>'
            f'</soap:Envelope>').encode()


def _registros_soap(contenido: bytes, operacion: str) -> list[dict]:
    raiz = ET.fromstring(contenido)
    nodo = next((e for e in raiz.iter() if e.tag.endswith(operacion + "Result")), None)
    if nodo is None:
        raise ValueError(f"Respuesta SMV sin nodo {operacion}Result")
    texto = (nodo.text or "").strip()
    if not texto:
        return []
    datos = json.loads(texto)
    if isinstance(datos, dict):
        listas = [v for v in datos.values() if isinstance(v, list)]
        datos = listas[0] if len(listas) == 1 else [datos]
    return datos or []


def _soap(estado: str, ejercicio: int, periodo: str, tipo: str) -> tuple[pd.DataFrame, Fuente]:
    op = OPERACIONES[estado]
    destino = CARPETA / "soap" / f"{op}_{ejercicio}_{periodo}_{tipo}.xml"
    f = descargar(SOAP_URL, destino, "smv", metodo="POST", datos=_sobre(op, ejercicio, periodo, tipo),
                  cabeceras={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{NS_TEMPURI}{op}"'},
                  validar=lambda b: _registros_soap(b, op),
                  max_edad_horas=None if ejercicio < pd.Timestamp.now().year - 1 else 24 * 7,
                  timeout=(15, 300),
                  nota=f"SMV datos abiertos, {op} Ejercicio={ejercicio} Periodo={periodo} Tipo={tipo}")
    f.url = f"{SOAP_URL}#{op}?Ejercicio={ejercicio}&Periodo={periodo}&Tipo={tipo}"
    regs = _registros_soap(Path(f.archivo).read_bytes(), op)
    df = pd.DataFrame(regs)
    if df.empty:
        return df, f
    df = df.rename(columns={"RPJ": "rpj", "Cuenta": "cuenta", "DescripcionCuenta": "descripcion",
                            "Monto1": "monto", "Monto2": "monto_comparativo", "Moneda": "moneda",
                            "NombreEmpresa": "nombre"})
    df["rpj"] = df["rpj"].astype(str).str.strip()
    df["cuenta"] = df["cuenta"].astype(str).str.strip()
    df["estado"] = estado
    for c in ("monto", "monto_comparativo"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df, f


# ---------------------------------------------------------------- vía 2: espejo GitHub
def _espejo(ejercicio: int) -> tuple[pd.DataFrame, Fuente]:
    f = descargar(f"{ESPEJO}/hechos/ejercicio={ejercicio}/part-0.parquet",
                  CARPETA / "espejo" / f"hechos_{ejercicio}.parquet", "smv",
                  max_edad_horas=None if ejercicio < pd.Timestamp.now().year - 1 else 24 * 7,
                  nota="Espejo smv-eeff (AtlasLedger) del servicio de datos abiertos SMV; ODbL")
    df = pd.read_parquet(f.archivo)
    df["rpj"] = df["rpj"].astype(str).str.strip()
    return df, f


# ---------------------------------------------------------------- API pública
def estados(rpj: str, ejercicio: int, periodo: str = "A", tipo: str = "C",
            via: str = "auto") -> tuple[pd.DataFrame, Fuente, str]:
    """Devuelve (cuentas BG+ER de la empresa, fuente, tipo_usado).

    tipo: 'C' consolidado (preferido) o 'I' individual. Si no hay consolidado, cae a individual.
    via: 'auto' (SMV en vivo y si falla, espejo) | 'smv' | 'espejo'.
    """
    rpj = rpj.strip()
    tipos = [tipo] + (["I"] if tipo == "C" else [])
    errores = []
    if via in ("auto", "smv"):
        try:
            for t in tipos:
                partes, fuentes, por_estado = [], [], {}
                for est in ("BG", "ER"):
                    df, f = _soap(est, ejercicio, periodo, t)
                    if not df.empty:
                        partes.append(df[df["rpj"] == rpj])
                        fuentes.append(f)
                        por_estado[est] = f
                if partes and sum(len(p) for p in partes):
                    out = pd.concat(partes, ignore_index=True)
                    emitir("smv", f"SMV en vivo: {len(out)} cuentas de {rpj} {ejercicio}-{periodo} tipo {t}")
                    out = _ordenar(out)
                    out.attrs["fuente_por_estado"] = por_estado
                    return out, fuentes[0], t
            errores.append("SMV en vivo: sin registros para esa empresa/periodo")
        except Exception as e:  # noqa: BLE001
            errores.append(f"SMV en vivo falló: {e}")
            emitir("aviso", f"SMV en vivo no disponible ({e}); uso el espejo smv-eeff")
            if via == "smv":
                raise
    df, f = _espejo(ejercicio)
    for t in tipos:
        sub = df[(df["rpj"] == rpj) & (df["periodo"] == periodo) & (df["tipo"] == t) &
                 (df["estado"].isin(["BG", "ER"]))]
        if len(sub):
            sub = sub.merge(cuentas()[["cuenta", "descripcion", "orden"]], on="cuenta", how="left")
            emitir("smv", f"Espejo smv-eeff: {len(sub)} cuentas de {rpj} {ejercicio}-{periodo} tipo {t}")
            if t != tipo:
                emitir("aviso", f"No hay estados tipo {tipo} para {rpj} {ejercicio}; se usan tipo {t} (individual)")
            return _ordenar(sub), f, t
    raise LookupError(f"Sin estados para RPJ {rpj} {ejercicio}-{periodo}. " + " | ".join(errores))


def _ordenar(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ["estado", "cuenta", "descripcion", "monto", "monto_comparativo", "orden", "moneda"]
            if c in df]
    df = df[cols].copy()
    if "orden" not in df:
        df["orden"] = range(len(df))
    return df.sort_values(["estado", "orden"]).reset_index(drop=True)


def plan_de_cuentas(df: pd.DataFrame) -> str:
    """Letra del plan de cuentas SMV (2.º carácter del código más frecuente): D, F, E, A, I, V…"""
    letras = df["cuenta"].astype(str).str[1]
    return letras.mode().iat[0] if len(letras) else "D"


def cuentas_concepto(df: pd.DataFrame, concepto: str) -> list[str]:
    """Cuentas del DataFrame que componen el concepto, según el plan de cuentas (o por descripción)."""
    plan = plan_de_cuentas(df)
    presentes = set(df["cuenta"].astype(str))
    mapa = CONCEPTOS_POR_PLAN.get(plan, {})
    if concepto in mapa:
        opciones = mapa[concepto]
        if not opciones:
            return []
        if not isinstance(opciones[0], list):
            opciones = [opciones]
        for alt in opciones:
            ctas = [c for c in alt if c in presentes]
            if ctas:
                return ctas
        return []          # plan conocido: si no está la cuenta, no se adivina por descripción
    if concepto not in DESCRIPCIONES:
        return []
    prefijo, patron = DESCRIPCIONES[concepto]
    import re
    rx = re.compile(patron)
    cand = [str(r.cuenta) for r in df.itertuples()
            if str(r.cuenta).startswith(prefijo) and "descripcion" in df and rx.search(_norm(r.descripcion))]
    if concepto.endswith("_cp"):
        cand = [c for c in cand if c[2:4] < _ultimo_codigo_corriente(df)]
    elif concepto.endswith("_lp"):
        cand = [c for c in cand if c[2:4] >= _ultimo_codigo_corriente(df)]
    return cand[:1]


def _ultimo_codigo_corriente(df: pd.DataFrame) -> str:
    """Grupo (caracteres 3-4) del total de pasivo corriente: lo que viene después es no corriente."""
    for r in df.itertuples():
        if str(r.cuenta).startswith("1") and "descripcion" in df and \
                _norm(r.descripcion).startswith(("TOTAL PASIVO CORRIENTE", "TOTAL PASIVOS CORRIENTES",
                                                 "TOTAL DE PASIVOS CORRIENTES")):
            return str(r.cuenta)[2:4] + "~"
    return "04"


def conceptos(df: pd.DataFrame, comparativo: bool = False) -> dict[str, float | None]:
    """Extrae los conceptos clave de un DataFrame devuelto por `estados` (cualquier plan de cuentas)."""
    col = "monto_comparativo" if comparativo else "monto"
    idx = df.drop_duplicates("cuenta").set_index("cuenta")[col]
    plan = plan_de_cuentas(df)
    nombres = set(CONCEPTOS_D) | set(CONCEPTOS_POR_PLAN.get(plan, {}))
    out = {}
    for nombre in nombres:
        vals = [idx.get(c) for c in cuentas_concepto(df, nombre)]
        if any(pd.notna(v) for v in vals):
            out[nombre] = float(sum(v for v in vals if pd.notna(v)))
        else:
            out[nombre] = 0.0 if nombre in CONCEPTOS_OPCIONALES_CERO else None
    if out.get("pasivos_con_costo") is None:
        out["pasivos_con_costo"] = (out["otros_pasivos_financieros_cp"] or 0) + (out["otros_pasivos_financieros_lp"] or 0)
    return out


def dato_concepto(df: pd.DataFrame, fuente: Fuente, concepto: str, rpj: str, ejercicio: int,
                  comparativo: bool = False) -> Dato:
    ctas = cuentas_concepto(df, concepto)
    # En vivo, el balance (BG) y los resultados (ER) vienen de archivos distintos de la SMV
    es_er = (ctas[0] if ctas else ("2" if concepto in ("ingresos", "utilidad_operativa", "gastos_financieros",
                                                        "utilidad_neta") else "1")).startswith("2")
    fuente = df.attrs.get("fuente_por_estado", {}).get("ER" if es_er else "BG", fuente)
    v = conceptos(df, comparativo)[concepto]
    anio = ejercicio - 1 if comparativo else ejercicio
    cuentas_txt = "+".join(ctas) if ctas else "sin cuenta en la SMV (se toma 0)"
    return Dato(v, fuente, detalle=f"SMV RPJ {rpj}, ejercicio {anio}, cuenta(s) {cuentas_txt} ({concepto}), "
                                   f"plan {plan_de_cuentas(df)}")
