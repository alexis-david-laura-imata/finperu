"""Busca y descarga el PDF de los EEFF auditados ("Estados Financieros y Dictamen") desde el portal SIMV.

Ruta (verificada el 07/11/2026 en www.smv.gob.pe):
  SIMV → Emisores → Mercado Principal → Información Financiera
  Empresa (MainContent_cboDenominacionSocial, provoca postback)
  Tipo:    MainContent_cboTipo_0 = Individual (I) · MainContent_cboTipo_1 = Consolidada (C)
  Periodo: MainContent_cboPeriodo_1 = Anual (A)
  Año:     MainContent_cboAnio
  Buscar:  MainContent_cbBuscar
  Resultado: tabla con filas "Estados Financieros y Dictamen" → enlace ConsultasP8/documento.aspx?vidDoc={GUID}
             que redirige a ConsultasP8/temp/<nombre>.pdf

El portal es ASP.NET (postbacks), por eso se usa un navegador real (Playwright). Con visible=True
se ve el recorrido en pantalla. El enlace encontrado se guarda en caché para no repetir la búsqueda.
"""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from pathlib import Path

from .. import config
from ..eventos import emitir
from .red import Fuente, descargar

FORMULARIO = "https://www.smv.gob.pe/SIMV/Frm_InformacionFinanciera?data=A70181B60967D74090DCD93C4920AA1D769614EC12"
INICIO = "https://www.smv.gob.pe/SIMV/Default.aspx"
CARPETA = config.CACHE / "smv" / "pdf"
ES_DICTAMEN = re.compile(r"dictamen|auditad", re.I)
NO_ES = re.compile(r"xbrl|carta|comunica|memoria", re.I)


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().upper()
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", t).split())


def _fecha(d: dict):
    from datetime import datetime
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})\s*([ap])", d.get("fecha", ""), re.I)
    if not m:
        return datetime.min
    dd, mm, aa, h, mi, se, ap = m.groups()
    h = int(h) % 12 + (12 if ap.lower() == "p" else 0)
    return datetime(int(aa), int(mm), int(dd), h, int(mi), int(se))


def _valida_pdf(b: bytes) -> None:
    if not b.startswith(b"%PDF"):
        raise ValueError("La SMV no devolvió un PDF")


def _elegir_opcion(opciones: list[tuple[str, str]], nombre: str) -> tuple[str, str]:
    """opciones: [(value, texto)]. Busca la empresa por nombre normalizado."""
    n = _norm(nombre)
    for v, t in opciones:
        if _norm(t) == n:
            return v, t
    for v, t in opciones:
        if _norm(t).startswith(n) or n.startswith(_norm(t)):
            return v, t
    textos = [_norm(t) for _, t in opciones]
    mejor = difflib.get_close_matches(n, textos, n=1, cutoff=0.6)
    if mejor:
        i = textos.index(mejor[0])
        return opciones[i]
    raise LookupError(f"No encontré '{nombre}' en la lista de empresas del portal SMV")


_FIN_POSTBACK = """() => !(window.Sys && Sys.WebForms && Sys.WebForms.PageRequestManager &&
                       Sys.WebForms.PageRequestManager.getInstance().get_isInAsyncPostBack())"""


def _esperar(pag, ms: int = 400) -> None:
    """El formulario usa UpdatePanel (postback parcial): esperar a que termine."""
    pag.wait_for_timeout(ms)
    pag.wait_for_function(_FIN_POSTBACK, timeout=90000)
    pag.wait_for_load_state("domcontentloaded")


def _buscar_en_pagina(pag, nombre_empresa: str, anio: int, tipo: str, cartel=None) -> list[dict]:
    aviso = cartel or (lambda t: emitir("navegador", t))
    pag.goto(FORMULARIO, wait_until="domcontentloaded", timeout=90000)
    if not pag.locator("#MainContent_cboDenominacionSocial").count():
        pag.goto(INICIO, wait_until="domcontentloaded", timeout=90000)
        pag.get_by_role("link", name=re.compile("Información Financiera")).first.click()
    aviso("SMV · Información Financiera: elijo la empresa")
    sel = pag.locator("#MainContent_cboDenominacionSocial")
    opciones = sel.locator("option").evaluate_all("os => os.map(o => [o.value, o.textContent.trim()])")
    valor, texto = _elegir_opcion([tuple(o) for o in opciones if o[0] != "-1"], nombre_empresa)
    emitir("navegador", f"Empresa en el portal: {texto}")
    sel.select_option(valor)                          # postback parcial
    _esperar(pag)
    pag.locator("#MainContent_cboTipo_1" if tipo == "C" else "#MainContent_cboTipo_0").check()
    _esperar(pag, 200)
    pag.locator("#MainContent_cboPeriodo_1").check()      # Anual
    _esperar(pag)
    pag.locator("#MainContent_cboAnio").select_option(str(anio))
    _esperar(pag, 200)
    aviso(f"SMV · Busco estados {'consolidados' if tipo == 'C' else 'individuales'} anuales {anio}")
    pag.locator("#MainContent_cbBuscar").click()
    _esperar(pag, 800)
    filas = pag.locator("table tr").evaluate_all("""trs => trs.map(tr => {
        const td = [...tr.querySelectorAll('td')].map(x => x.innerText.trim());
        const a = tr.querySelector('a[href*="documento.aspx"], a[href*="ConsultasP8"]');
        return {celdas: td, url: a ? a.href : null};
    })""")
    docs = [{"empresa": f["celdas"][0], "documento": f["celdas"][1], "expediente": f["celdas"][2],
             "fecha": f["celdas"][3], "url": f["url"]}
            for f in filas if len(f["celdas"]) >= 4 and f["url"]]
    emitir("navegador", f"{len(docs)} documentos encontrados")
    return docs


def buscar_documentos(nombre_empresa: str, anio: int, tipo: str = "C", visible: bool = True,
                      velocidad: float = 1.0, nav=None) -> list[dict]:
    """Devuelve las filas de la tabla de resultados: [{documento, expediente, fecha, url}].
    Si se pasa `nav` (motor.navegador.sesion.Navegador) usa esa ventana; si no, abre una."""
    if nav is not None:
        docs = _buscar_en_pagina(nav.page, nombre_empresa, anio, tipo, nav.cartel)
        fila = nav.page.locator("tr", has_text=re.compile("Dictamen|Auditad", re.I))
        nav.resaltar(fila, "SMV · Este es el PDF de los estados financieros auditados", 1.8)
        return docs
    from ..navegador.sesion import Navegador
    with Navegador(visible, velocidad) as n:
        return buscar_documentos(nombre_empresa, anio, tipo, nav=n)


def pdf_auditado(rpj: str, nombre_empresa: str, anio: int, tipo: str = "C", visible: bool = True,
                 nav=None, velocidad: float = 1.0) -> tuple[Fuente, dict]:
    """Descarga el PDF auditado (y el XBRL si existe). Devuelve (Fuente del PDF, info del documento)."""
    CARPETA.mkdir(parents=True, exist_ok=True)
    cache = CARPETA / f"{rpj}_{anio}_{tipo}.json"
    if cache.exists() and nav is None:
        info = json.loads(cache.read_text(encoding="utf-8"))
        emitir("cache", f"Enlace del PDF auditado ya conocido: {info['documento']} ({info['fecha']})")
    else:
        info = None
        for t in ([tipo] + (["I"] if tipo == "C" else [])):
            docs = buscar_documentos(nombre_empresa, anio, t, visible, velocidad, nav)
            cand = [d for d in docs if ES_DICTAMEN.search(d["documento"]) and not NO_ES.search(d["documento"])]
            if cand:
                info = {**sorted(cand, key=_fecha)[-1], "tipo": t}  # el más reciente (por si hubo reemplazo)
                xbrl = [d for d in docs if re.search("xbrl", d["documento"], re.I)]
                if xbrl:
                    info["xbrl_url"] = sorted(xbrl, key=_fecha)[-1]["url"]
                break
            emitir("aviso", f"No hay 'Estados Financieros y Dictamen' tipo {t} para {anio}")
        if not info:
            raise LookupError(f"No encontré el PDF auditado de {nombre_empresa} {anio} en la SMV.")
        cache.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    destino = CARPETA / f"{rpj}_{anio}_{info['tipo']}_auditado.pdf"
    f = descargar(info["url"], destino, "smv", validar=_valida_pdf, timeout=(15, 300),
                  nota=f"SMV · {info['documento']} · expediente {info['expediente']} · presentado {info['fecha']}")
    if info.get("xbrl_url"):
        try:
            fx = descargar(info["xbrl_url"], CARPETA / f"{rpj}_{anio}_{info['tipo']}_xbrl.zip", "smv",
                           timeout=(15, 300), nota=f"SMV · Archivo estructurado XBRL · expediente {info['expediente']}")
            info["xbrl_archivo"] = fx.archivo
        except Exception as e:  # noqa: BLE001
            emitir("aviso", f"No se pudo descargar el XBRL: {e}")
    return f, info
