"""Recorrido autónomo: navega por cada fuente y descarga todo lo que el modelo necesita.

Orden (igual que en la Guía del curso):
  1. SMV        → Información Financiera → "Estados Financieros y Dictamen" (PDF) + XBRL
  2. Damodaran  → Data: Archives → "Levered and Unlevered Betas by Industry" → Emerging Markets → 1/AA+1
                  (o Data: Current si el año aún no está archivado)
  3. Damodaran  → Data: Current → Historical Returns (histretSP.xls)
  4. Tesoro     → Daily Treasury Par Yield Curve Rates del año → CSV
  5. BCRP       → PN01129XM (EMBIG Perú) y PN01273PM (IPC Lima), fila de diciembre

Los archivos quedan en la caché con el mismo nombre que usa el motor, así el cálculo
posterior usa EXACTAMENTE lo que se descargó (y queda en la hoja Fuentes y en /evidencias).
Si un paso visual falla, se descarga igual por la vía directa: el modelo nunca se queda sin datos.
"""
from __future__ import annotations

import re
from datetime import datetime

from .. import config
from ..datos import bcrp, damodaran, smv, tesoro
from ..datos.damodaran import BASE as DAMODARAN_PC, REGIONES, anio_archivo_para
from ..eventos import emitir
from .sesion import Navegador

DAM_ARCHIVO = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/dataarchived.html"
DAM_ACTUAL = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datacurrent.html"
TESORO_VISTA = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView"
                "?type=daily_treasury_par_yield_curve&field_tdr_date_value={a}")
BCRP_VISTA = "https://estadisticas.bcrp.gob.pe/estadisticas/series/mensuales/resultados/{c}/html"
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"]


def _paso(nombre: str, fn, resumen: dict):
    try:
        r = fn()
        resumen[nombre] = {"ok": True, **(r or {})}
    except Exception as e:  # noqa: BLE001
        emitir("aviso", f"Recorrido · {nombre}: {e} (se usará la descarga directa)")
        resumen[nombre] = {"ok": False, "error": str(e)}


def recorrer(rpj: str, anio: int, *, region: str = "emerg", vintage: str = "cierre_siguiente",
             visible: bool = True, velocidad: float = 1.0, incluir_smv_pdf: bool = True) -> dict:
    """Ejecuta el recorrido. Devuelve un resumen por fuente (ok/errores, archivos, info del PDF)."""
    emp = next((e for e in smv.buscar_empresa(rpj) if e["rpj"] == rpj), {"rpj": rpj, "nombre": rpj})
    resumen: dict = {"empresa": emp.get("nombre"), "anio": anio}
    emitir("inicio", f"Recorrido autónomo de fuentes para {emp.get('nombre')} {anio}")

    with Navegador(visible, velocidad) as nav:
        p = nav.page

        # 1. SMV ---------------------------------------------------------------------------
        if incluir_smv_pdf:
            def smv_paso():
                from ..datos.smv_pdf import pdf_auditado
                df, _, tipo = smv.estados(rpj, anio)            # define consolidado / individual
                f, info = pdf_auditado(rpj, emp["nombre"], anio, tipo, visible, nav=nav, velocidad=velocidad)
                return {"pdf": f.archivo, "pdf_url": f.url, "info": info, "tipo": tipo}
            _paso("smv", smv_paso, resumen)

        # 2. Damodaran: betas --------------------------------------------------------------
        nombre = REGIONES[region]
        aa = anio_archivo_para(anio, vintage) % 100

        def betas_paso():
            nav.ir(DAM_ARCHIVO, "Damodaran · Data: Archives")
            nav.resaltar(p.get_by_text("Levered and Unlevered Betas by Industry"),
                         "Damodaran · Levered and Unlevered Betas by Industry", 1.2)
            enlace = p.locator(f'a[href$="{nombre}{aa:02d}.xls"]')
            if enlace.count():
                url = f"{DAMODARAN_PC}/archives/{nombre}{aa:02d}.xls"
                nav.resaltar(enlace, f"Damodaran · {nombre}{aa:02d}.xls = betas con datos de 20{aa:02d} "
                                     f"(publicado el 1/{(aa + 1) % 100:02d})", 1.6)
                destino = damodaran.CARPETA / f"{nombre}{aa:02d}.xls"
            else:
                nav.ir(DAM_ACTUAL, f"Damodaran · 20{aa:02d} aún no está archivado: uso Data: Current")
                enlace = p.locator(f'a[href$="datasets/{nombre}.xls"]')
                url = f"{DAMODARAN_PC}/datasets/{nombre}.xls"
                nav.resaltar(enlace, f"Damodaran · {nombre}.xls (vigente)", 1.6)
                destino = damodaran.CARPETA / f"{nombre}_actual_{datetime.now():%Y%m}.xls"
            f = nav.descargar_clic(enlace, destino, url, "damodaran",
                                   nota=f"Descargado por el navegador desde {DAM_ARCHIVO if 'archives' in url else DAM_ACTUAL}")
            return {"archivo": f.archivo}
        _paso("damodaran_betas", betas_paso, resumen)

        # 3. Damodaran: retornos históricos ------------------------------------------------
        def histret_paso():
            nav.ir(DAM_ACTUAL, "Damodaran · Data: Current")
            enlace = p.locator('a[href$="histretSP.xls"]')
            nav.resaltar(enlace, "Damodaran · Historical Returns on Stocks, Bonds and Bills (histretSP.xls)", 1.6)
            destino = damodaran.CARPETA / f"histretSP_actual_{datetime.now():%Y%m}.xls"
            f = nav.descargar_clic(enlace, destino, f"{DAMODARAN_PC}/datasets/histretSP.xls", "damodaran",
                                   nota=f"Descargado por el navegador desde {DAM_ACTUAL}")
            return {"archivo": f.archivo}
        _paso("damodaran_histret", histret_paso, resumen)

        # 4. Tesoro ------------------------------------------------------------------------
        def tesoro_paso():
            nav.ir(TESORO_VISTA.format(a=anio), f"Tesoro EE.UU. · Daily Par Yield Curve {anio}", espera="load")
            p.wait_for_timeout(2500)
            nav.resaltar(p.locator("table tbody tr").last, f"Tesoro · último día hábil de {anio}: columna 10 Yr", 1.6)
            d = tesoro.rf_10y(anio)                              # descarga el CSV oficial del año
            nav.cartel(f"Tesoro · Rf 10 años al {d.extra['fecha']} = {d.valor:.2%}")
            nav.pausa(1.0)
            return {"archivo": d.fuente.archivo, "valor": d.valor}
        _paso("tesoro", tesoro_paso, resumen)

        # 5. BCRP --------------------------------------------------------------------------
        def bcrp_paso():
            out = {}
            for codigo, titulo, fn in ((bcrp.RIESGO_PAIS, "Riesgo país (EMBIG Perú)", bcrp.riesgo_pais),
                                       (bcrp.INFLACION_PE, "Inflación Perú (IPC Lima, 12 meses)", bcrp.inflacion_peru)):
                nav.ir(BCRP_VISTA.format(c=codigo), f"BCRP · {codigo} · {titulo}", espera="load")
                etiqueta = f"Dic{anio % 100:02d}"
                nav.resaltar(p.locator("tr", has_text=re.compile(rf"\b{etiqueta}\b")),
                             f"BCRP · {titulo}: valor de {etiqueta}", 1.6)
                d = fn(anio)
                out[codigo] = {"archivo": d.fuente.archivo, "valor": d.valor}
            return out
        _paso("bcrp", bcrp_paso, resumen)

        nav.cartel("Recorrido terminado · todas las fuentes descargadas")
        nav.pausa(1.2)

    ok = sum(1 for v in resumen.values() if isinstance(v, dict) and v.get("ok"))
    emitir("navegador", f"Recorrido terminado: {ok} fuentes recorridas con el navegador")
    return resumen
