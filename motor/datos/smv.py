"""Estados financieros de la SMV (Superintendencia del Mercado de Valores del Perú).

Dos vías, en este orden:
1. EN VIVO: servicio de datos abiertos SOAP de la SMV (mvnet.smv.gob.pe). Devuelve TODAS las
   empresas de un periodo; se cachea y se filtra por RPJ.
2. ESPEJO: base abierta smv-eeff (AtlasLedger, GitHub), que replica ese mismo servicio y se
   actualiza cada mes. Se usa si la SMV no responde.
   Atribución requerida (ODbL): datos de la SMV; base derivada smv-eeff.

Cuentas del plan "D" (empresas en general) que usa la metodología del curso:
  1D0309 Otros pasivos financieros (corriente)     1D0401 Otros pasivos financieros (no corriente)
  1D07ST Total patrimonio                           2D03ST Ganancia (pérdida) operativa
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

# Conceptos clave (plan D) -> cuentas SMV que lo componen
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


def conceptos(df: pd.DataFrame, comparativo: bool = False) -> dict[str, float]:
    """Extrae los conceptos clave (plan D) de un DataFrame devuelto por `estados`."""
    col = "monto_comparativo" if comparativo else "monto"
    idx = df.set_index("cuenta")[col]
    out = {}
    for nombre, ctas in CONCEPTOS_D.items():
        vals = [idx.get(c) for c in ctas]
        out[nombre] = float(sum(v for v in vals if pd.notna(v))) if any(pd.notna(v) for v in vals) else None
    return out


def dato_concepto(df: pd.DataFrame, fuente: Fuente, concepto: str, rpj: str, ejercicio: int,
                  comparativo: bool = False) -> Dato:
    ctas = CONCEPTOS_D[concepto]
    # En vivo, el balance (BG) y los resultados (ER) vienen de archivos distintos de la SMV
    fuente = df.attrs.get("fuente_por_estado", {}).get("ER" if ctas[0].startswith("2") else "BG", fuente)
    v = conceptos(df, comparativo)[concepto]
    anio = ejercicio - 1 if comparativo else ejercicio
    return Dato(v, fuente, detalle=f"SMV RPJ {rpj}, ejercicio {anio}, cuenta(s) {'+'.join(ctas)} ({concepto})")
