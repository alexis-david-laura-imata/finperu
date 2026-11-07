"""API de series estadísticas del BCRP (sin clave).

Formato: https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{CODIGOS}/json/{inicio}/{fin}/{idioma}
Series que usa la metodología del curso:
- PN01129XM  Diferencial de rendimientos EMBIG Perú (pbs, mensual)  -> riesgo país, valor de DICIEMBRE
- PN01273PM  IPC Lima Metropolitana (var% 12 meses, mensual)        -> inflación Perú, valor de DICIEMBRE
"""
from __future__ import annotations

import json

from .. import config
from ..eventos import emitir
from .red import Dato, descargar

API = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"
CARPETA = config.CACHE / "bcrp"
RIESGO_PAIS = "PN01129XM"
INFLACION_PE = "PN01273PM"


def _valida(b: bytes) -> None:
    d = json.loads(b.decode("utf-8-sig"))
    if "periods" not in d:
        raise ValueError("Respuesta BCRP sin 'periods'")


def serie(codigo: str, inicio: str, fin: str) -> tuple[dict, "Fuente"]:  # noqa: F821
    """inicio/fin: 'AAAA-M' para mensuales, 'AAAA' para anuales."""
    url = f"{API}/{codigo}/json/{inicio}/{fin}/esp"
    f = descargar(url, CARPETA / f"{codigo}_{inicio}_{fin}.json", "bcrp", validar=_valida,
                  max_edad_horas=24 * 7)
    d = json.loads(open(f.archivo, encoding="utf-8-sig").read())
    return d, f


def valor_mensual(codigo: str, anio: int, mes: int = 12) -> Dato:
    d, f = serie(codigo, f"{anio}-{mes}", f"{anio}-{mes}")
    periodos = d.get("periods", [])
    if not periodos:
        raise LookupError(f"BCRP {codigo}: sin dato para {anio}-{mes:02d}")
    p = periodos[-1]
    v = p["values"][0]
    if v in ("n.d.", "", None):
        raise LookupError(f"BCRP {codigo}: valor no disponible para {p['name']}")
    titulo = d.get("config", {}).get("series", [{}])[0].get("name", codigo)
    return Dato(float(v), f, detalle=f"BCRP {codigo} – {titulo} – {p['name']}")


def riesgo_pais(anio: int, mes: int = 12) -> Dato:
    d = valor_mensual(RIESGO_PAIS, anio, mes)
    pbs = d.valor
    d.valor = pbs / 10000
    d.detalle += f": {pbs:.0f} pbs → {d.valor:.4%}"
    d.extra["pbs"] = pbs
    emitir("bcrp", f"Riesgo país Perú {anio}-{mes:02d} = {pbs:.0f} pbs")
    return d


def inflacion_peru(anio: int, mes: int = 12) -> Dato:
    d = valor_mensual(INFLACION_PE, anio, mes)
    pct = d.valor
    d.valor = pct / 100
    d.detalle += f": {pct:.2f}% (variación 12 meses a diciembre)"
    emitir("bcrp", f"Inflación Perú {anio} (dic/dic) = {pct:.2f}%")
    return d
