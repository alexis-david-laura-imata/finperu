"""Datos de Aswath Damodaran (NYU Stern).

- Betas por industria: betaemerg / betas (US) / betaGlobal. Archivo histórico por año:
  pc/archives/betaemerg{AA}.xls  ->  dataset publicado en enero de 20AA+1 (datos del año 20AA).
  Ej.: betaemerg23.xls está fechado el 5-ene-2024 (verificado con el archivo del curso).
- Retornos históricos EE.UU.: histretSP.xls, hoja "Returns by year" (S&P 500 y T-Bond 10 años,
  desde 1928). Con eso se calcula la prima de mercado como en el curso.

Regla de "vintage" (qué archivo usar para estados financieros del año N):
- cierre_siguiente (por defecto, práctica Laive 2023): betaemerg{N}.xls  (publicado ene N+1)
- disponible_al_cierre (modelo Laive 2021):          betaemerg{N-1}.xls (publicado ene N)
"""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

import xlrd

from .. import config
from ..eventos import emitir
from .red import Dato, Fuente, descargar, fuente_local

BASE = "https://pages.stern.nyu.edu/~adamodar/pc"
CARPETA = config.CACHE / "damodaran"
REGIONES = {"emerg": "betaemerg", "us": "betas", "global": "betaGlobal"}


def _valida_xls(b: bytes) -> None:
    if not (b[:4] == b"\xd0\xcf\x11\xe0" or b[:2] == b"PK"):
        raise ValueError("La respuesta no es un archivo Excel (¿página de error?)")


def archivo(nombre: str, anio_archivo: int | None = None, local: Path | None = None) -> Fuente:
    """Descarga datasets/{nombre}.xls (actual) o archives/{nombre}{AA}.xls (histórico)."""
    if local:
        return fuente_local(local, "damodaran", nota="Archivo local del curso")
    if anio_archivo is None:
        url = f"{BASE}/datasets/{nombre}.xls"
        destino = CARPETA / f"{nombre}_actual_{datetime.now():%Y%m}.xls"
        return descargar(url, destino, "damodaran", max_edad_horas=24 * 30, validar=_valida_xls)
    aa = anio_archivo % 100
    url = f"{BASE}/archives/{nombre}{aa:02d}.xls"
    return descargar(url, CARPETA / f"{nombre}{aa:02d}.xls", "damodaran", validar=_valida_xls)


def _fecha_excel(v) -> str:
    try:
        return xlrd.xldate_as_datetime(float(v), 0).date().isoformat()
    except Exception:  # noqa: BLE001
        return str(v)


def _tabla_industrias(ruta: str) -> tuple[list[str], list[list], str]:
    wb = xlrd.open_workbook(ruta)
    hoja = next(s for s in wb.sheets() if "Industry" in s.name)
    fecha = ""
    if hoja.nrows and "Date updated" in str(hoja.cell_value(0, 0)):
        fecha = _fecha_excel(hoja.cell_value(0, 1))
    for r in range(min(hoja.nrows, 40)):
        if str(hoja.cell_value(r, 0)).strip() == "Industry Name":
            cab = [str(c.value).strip() for c in hoja.row(r)]
            filas = [hoja.row_values(i) for i in range(r + 1, hoja.nrows) if str(hoja.cell_value(i, 0)).strip()]
            return cab, filas, fecha
    raise ValueError(f"No encontré la tabla 'Industry Name' en {ruta}")


def anio_archivo_para(anio_ef: int, vintage: str) -> int:
    return anio_ef if vintage == "cierre_siguiente" else anio_ef - 1


def industrias(region: str = "emerg", anio_ef: int | None = None, vintage: str = "cierre_siguiente") -> list[str]:
    try:
        ruta = _archivo_betas(region, anio_ef, vintage).archivo
    except ConnectionError:
        # Sin internet: cualquier archivo de betas ya descargado o del curso sirve para la lista
        locales = sorted(CARPETA.glob(f"{REGIONES[region]}*.xls")) + sorted(config.FUENTE_CURSO.glob("beta*.xls"))
        if not locales:
            raise
        ruta = str(locales[-1])
    _, filas, _ = _tabla_industrias(ruta)
    return [str(x[0]).strip() for x in filas]


def _archivo_betas(region: str, anio_ef: int | None, vintage: str, local: Path | None = None) -> Fuente:
    nombre = REGIONES[region]
    if local or anio_ef is None:
        return archivo(nombre, None, local)
    aa = anio_archivo_para(anio_ef, vintage)
    try:
        return archivo(nombre, aa)
    except ConnectionError:
        # El año más reciente aún no está en "archives": es el dataset actual
        emitir("aviso", f"No existe {nombre}{aa % 100:02d}.xls en archivos; uso el dataset actual")
        f = archivo(nombre, None)
        f.nota = (f"Se pidió {nombre}{aa % 100:02d}.xls (datos de {aa}), que aún no está en 'archives': "
                  f"se usa el dataset vigente, que es esa misma publicación.")
        return f


def beta_desapalancada(industria: str, anio_ef: int, region: str = "emerg",
                       vintage: str = "cierre_siguiente", columna: str = "Unlevered beta",
                       local: Path | None = None) -> Dato:
    f = _archivo_betas(region, anio_ef, vintage, local)
    cab, filas, fecha = _tabla_industrias(f.archivo)
    try:
        j = next(i for i, c in enumerate(cab) if c.lower() == columna.lower())
    except StopIteration:
        raise ValueError(f"Columna '{columna}' no existe. Columnas: {cab[:9]}")
    obj = industria.strip().lower()
    fila = next((x for x in filas if str(x[0]).strip().lower() == obj), None)
    if fila is None:
        parecidas = [str(x[0]) for x in filas if obj.split()[0] in str(x[0]).lower()][:8]
        raise LookupError(f"Industria '{industria}' no encontrada. ¿Quisiste decir: {parecidas}?")
    v = float(fila[j])
    emitir("damodaran", f"Beta desapalancada {industria} ({Path(f.archivo).name}, {fecha}) = {v:.4f}")
    return Dato(v, f, detalle=f"Damodaran {Path(f.archivo).name} (actualizado {fecha}), "
                              f"industria '{fila[0]}', columna '{cab[j]}'",
                extra={"fecha_archivo": fecha, "n_empresas": fila[1], "vintage": vintage})


# ---------------------------------------------------------------- retornos históricos
def _retornos(local: Path | None = None) -> tuple[dict[int, dict[str, float]], Fuente]:
    f = archivo("histretSP", None, local)
    wb = xlrd.open_workbook(f.archivo)
    s = wb.sheet_by_name("Returns by year")
    for r in range(min(s.nrows, 40)):
        if str(s.cell_value(r, 0)).strip() == "Year":
            cab = [str(c.value).strip() for c in s.row(r)]
            break
    else:
        raise ValueError("histretSP: no encontré la fila 'Year'")

    def col(prefijo: str) -> int:
        return next(i for i, c in enumerate(cab) if c.lower().startswith(prefijo.lower()))

    c_sp, c_tb = col("S&P 500 (includes dividends)"), col("US T. Bond")
    c_inf = next((i for i, c in enumerate(cab) if c.lower() == "inflation rate"), None)
    datos = {}
    for i in range(r + 1, s.nrows):
        y = s.cell_value(i, 0)
        if not isinstance(y, float) or y < 1900:
            if datos:
                break
            continue
        datos[int(y)] = {"sp500": float(s.cell_value(i, c_sp)), "tbond": float(s.cell_value(i, c_tb)),
                         "inflacion": float(s.cell_value(i, c_inf)) if c_inf is not None else math.nan}
    return datos, f


def prima_mercado(anio: int, metodo: str = "aritmetico", desde: int = 1928,
                  local: Path | None = None) -> Dato:
    datos, f = _retornos(local)
    if anio not in datos:
        raise LookupError(f"histretSP solo llega hasta {max(datos)}; no tiene {anio}")
    anios = [y for y in range(desde, anio + 1) if y in datos]
    sp = [datos[y]["sp500"] for y in anios]
    tb = [datos[y]["tbond"] for y in anios]
    if metodo == "aritmetico":
        rm, rf = sum(sp) / len(sp), sum(tb) / len(tb)
    else:
        rm = math.prod(1 + x for x in sp) ** (1 / len(sp)) - 1
        rf = math.prod(1 + x for x in tb) ** (1 / len(tb)) - 1
    emitir("damodaran", f"Prima de mercado {desde}-{anio} ({metodo}) = {rm:.4%} - {rf:.4%} = {rm - rf:.4%}")
    return Dato(rm - rf, f, detalle=f"Damodaran histretSP, 'Returns by year', promedio {metodo} "
                                    f"{desde}-{anio}: S&P 500 {rm:.4%} − T-Bond 10a {rf:.4%}",
                extra={"rm": rm, "rf_hist": rf, "anios": len(anios)})


def inflacion_eeuu(anio: int, local: Path | None = None) -> Dato:
    datos, f = _retornos(local)
    v = datos[anio]["inflacion"]
    return Dato(v, f, detalle=f"Damodaran histretSP, columna 'Inflation Rate' (CPI EE.UU.) {anio}")
