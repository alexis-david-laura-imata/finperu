"""Orquestador: de "Laive 2023" a una carpeta con el Excel auditable.

    salidas/<Empresa>_<Año>_WACC_<fecha-hora>/
        <Empresa>_<Año>_WACC.xlsx
        receta.json          -> todo lo necesario para regenerar el mismo modelo
        resultados.json      -> resultados y controles
        evidencias/          -> copia de cada archivo fuente (SMV, Damodaran, BCRP, Tesoro)
"""
from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from . import __version__, config
from .eventos import emitir
from .metodologia import LineaDeuda, calcular, kd_desde_tabla, recolectar

NOMBRES_RESULTADO = {"wacc": "WACC", "ke": "Ke_Final", "roic": "ROIC", "eva": "Valor_EVA",
                     "estado": "Estado_Controles"}


def _slug(t: str) -> str:
    t = re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_")
    return t[:40] or "empresa"


def lineas_kd(kd: Any) -> Any:
    """Acepta float, lista de LineaDeuda o lista de dicts (desde el MCP / la web)."""
    if isinstance(kd, list):
        out = []
        for x in kd:
            if isinstance(x, LineaDeuda):
                out.append(x)
            else:
                out.append(LineaDeuda(tipo=x["tipo"], entidad=x["entidad"], tasa_min=float(x["tasa_min"]),
                                      tasa_max=None if x.get("tasa_max") in (None, "") else float(x["tasa_max"]),
                                      corriente=float(x.get("corriente") or 0),
                                      no_corriente=float(x.get("no_corriente") or 0),
                                      moneda=x.get("moneda", "S/"), nota=x.get("nota", "")))
        return out
    return kd


def excel_vivo_disponible() -> bool:
    if platform.system() != "Windows":
        return False
    try:
        import xlwings  # noqa: F401
        return True
    except ImportError:
        return False


def generar_wacc(rpj: str, anio: int, industria: str, *, kd: Any = None, parametros: dict | None = None,
                 sobrescribir: dict | None = None, modo: str = "auto", velocidad: float = 1.0,
                 via_smv: str = "auto", locales: dict | None = None, kd_pdf: dict | None = None,
                 ver_navegador: bool = False, ver_calculos: bool = False) -> dict:
    """Genera el modelo WACC + EVA.

    Opciones de visualización (combinables):
      modo='vivo'          → ver el Excel construirse celda por celda ('archivo' = sin abrir Excel)
      ver_navegador=True   → ver el navegador recorrer SMV, Damodaran, Tesoro y BCRP descargando todo
      ver_calculos=True    → ver cada cálculo en Python con su fórmula y números
      velocidad            → 0 sin pausas · 1 normal · 2-3 lento (presentaciones)
    kd: número, tabla (lista), 'pdf' (lee la nota de deuda del PDF auditado) o None (aproximado).
    """
    t0 = datetime.now()
    p = {**config.PARAMETROS_DEFECTO, **(parametros or {})}
    recorrido = None
    if ver_navegador:
        from .navegador.recorrido import recorrer
        recorrido = recorrer(rpj, anio, region=p["region_beta"], vintage=p["damodaran_vintage"],
                             visible=True, velocidad=velocidad, incluir_smv_pdf=True)
    if kd == "pdf":
        kd, kd_pdf = None, None
        try:
            r_pdf = kd_desde_pdf(rpj, anio, visible=False, via_smv=via_smv)
            if r_pdf.get("cuadra") and r_pdf.get("lineas") and all(l["tasa_min"] is not None for l in r_pdf["lineas"]):
                kd, kd_pdf = r_pdf["lineas"], r_pdf["kd_pdf"]
                emitir("pdf", f"Kd desde la nota de deuda del PDF: {r_pdf.get('kd_estimado', 0):.2%}")
            else:
                emitir("aviso", "La nota de deuda del PDF no cuadró con el balance; se usa el Kd aproximado.")
        except Exception as e:  # noqa: BLE001
            from .errores import falta_modulo
            emitir("aviso", f"No se pudo leer la nota de deuda del PDF ({falta_modulo(e) or e}); "
                            "se usa el Kd aproximado.")
    kd = lineas_kd(kd)
    ins = recolectar(rpj, anio, industria, kd=kd, parametros=parametros, sobrescribir=sobrescribir,
                     locales=locales, via_smv=via_smv, kd_pdf=kd_pdf)
    r = calcular(ins, mostrar=ver_calculos, velocidad=velocidad)

    vivo = modo == "vivo" or (modo == "auto" and excel_vivo_disponible())
    if vivo and not excel_vivo_disponible():
        raise RuntimeError("El modo en vivo necesita Windows con Excel y xlwings instalados.")
    from .excel.lienzo import LienzoArchivo, LienzoVivo
    from .excel.plantilla_wacc import construir
    L = LienzoVivo(velocidad) if vivo else LienzoArchivo()
    emitir("excel", f"Construyendo el modelo en modo {'EN VIVO' if vivo else 'archivo'}")
    info = construir(L, ins, r)

    nombre = ins.empresa.get("nombre", rpj)
    carpeta = config.SALIDAS / f"{_slug(nombre)}_{anio}_WACC_{t0:%Y%m%d_%H%M%S}"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_xlsx = carpeta / f"{_slug(nombre)}_{anio}_WACC.xlsx"
    L.guardar(ruta_xlsx)

    # Verificación: valores que calculó Excel vs Python
    verif = {}
    if vivo:
        app_wb = L.wb
        for k, nm in NOMBRES_RESULTADO.items():
            try:
                verif[k] = app_wb.names[nm].refers_to_range.value
            except Exception:  # noqa: BLE001
                verif[k] = None
    else:
        verif = recalcular_libreoffice(ruta_xlsx)

    # Evidencias
    ev = carpeta / "evidencias"
    ev.mkdir(exist_ok=True)
    copiados = set()
    extra = []
    sm = (recorrido or {}).get("smv") or {}
    if sm.get("ok"):
        extra += [sm.get("pdf"), (sm.get("info") or {}).get("xbrl_archivo")]
    for a in [fr.get("archivo") for fr in info["fuentes"]] + extra:
        if a and Path(a).exists() and a not in copiados:
            shutil.copy2(a, ev / Path(a).name)
            copiados.add(a)

    receta = {"herramienta": f"FinPerú MCP v{__version__}", "plantilla": "P1_WACC_EVA", "generado": t0.isoformat(),
              "rpj": rpj, "empresa": nombre, "anio": anio, "industria": industria, "parametros": ins.parametros,
              "sobrescribir": sobrescribir or {}, "via_smv": via_smv,
              "visualizacion": {"excel": vivo, "navegador": ver_navegador, "calculos": ver_calculos, "velocidad": velocidad},
              "kd": [asdict(x) for x in kd] if isinstance(kd, list) else kd, "kd_pdf": kd_pdf,
              "fuentes": [{k: v for k, v in f.items() if k != "valor"} for f in info["fuentes"]]}
    (carpeta / "receta.json").write_text(json.dumps(receta, ensure_ascii=False, indent=2, default=str), "utf-8")
    salida = {"carpeta": str(carpeta), "excel": str(ruta_xlsx), "modo": "vivo" if vivo else "archivo",
              "resultados": {k: r[k] for k in ("wacc", "ke", "ke_usd", "beta_l", "kd", "Wd", "We", "roic", "eva",
                                               "nopat", "ci_promedio", "roe", "eva_accionista",
                                               "patrimonio_promedio") if k in r},
              "controles": r["controles"], "avisos": r["avisos"], "verificacion_excel": verif,
              "recorrido": recorrido,
              "segundos": round((datetime.now() - t0).total_seconds(), 1)}
    (carpeta / "resultados.json").write_text(json.dumps(salida, ensure_ascii=False, indent=2, default=str), "utf-8")
    emitir("fin", f"Listo en {salida['segundos']} s → {ruta_xlsx}")
    return salida


def regenerar(ruta_receta: str | Path, modo: str = "auto", velocidad: float = 1.0) -> dict:
    """Vuelve a construir un modelo desde su receta.json."""
    rc = json.loads(Path(ruta_receta).read_text(encoding="utf-8"))
    return generar_wacc(rc["rpj"], rc["anio"], rc["industria"], kd=rc.get("kd"), parametros=rc.get("parametros"),
                        sobrescribir=rc.get("sobrescribir"), modo=modo, velocidad=velocidad,
                        via_smv=rc.get("via_smv", "auto"), kd_pdf=rc.get("kd_pdf"))


def recalcular_libreoffice(ruta: Path) -> dict:
    """Si hay LibreOffice, recalcula el archivo y lee los resultados (verificación sin Excel)."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return {}
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([soffice, "--headless", "--calc", "--convert-to", "xlsx", "--outdir", tmp, str(ruta)],
                       capture_output=True, timeout=120)
        out = Path(tmp) / ruta.name
        if not out.exists():
            return {}
        from openpyxl import load_workbook
        wb = load_workbook(out, data_only=True)
        res = {}
        for k, nm in NOMBRES_RESULTADO.items():
            try:
                dn = wb.defined_names[nm]
                hoja, celda = next(dn.destinations)
                res[k] = wb[hoja][celda.replace("$", "")].value
            except Exception:  # noqa: BLE001
                res[k] = None
        return res


def kd_desde_pdf(rpj: str, anio: int, *, visible: bool = True, archivo_pdf: str | Path | None = None,
                 via_smv: str = "auto") -> dict:
    """Busca el PDF auditado en la SMV (o usa `archivo_pdf`) y lee la nota de deuda.
    Devuelve {lineas, cuadra, total_extraido, deuda_esf, pagina, avisos, kd_pdf, kd_estimado}."""
    from .datos import smv
    from .datos.nota_deuda import extraer
    df, _, tipo = smv.estados(rpj, anio, via=via_smv)
    c, c0 = smv.conceptos(df), smv.conceptos(df, comparativo=True)
    d = (c["otros_pasivos_financieros_cp"] or 0) + (c["otros_pasivos_financieros_lp"] or 0)
    d0 = (c0["otros_pasivos_financieros_cp"] or 0) + (c0["otros_pasivos_financieros_lp"] or 0)
    gf = abs(c["gastos_financieros"] or 0)
    con_costo = (c["pasivos_con_costo"] or 0) + (c0["pasivos_con_costo"] or 0)   # en bancos incluye depósitos
    respaldo = gf / (con_costo / 2) if con_costo else None
    if archivo_pdf:
        ruta, url, info = Path(archivo_pdf), None, {"documento": "PDF subido por el usuario"}
    else:
        from .datos.smv_pdf import pdf_auditado
        emp = next((e for e in smv.buscar_empresa(rpj) if e["rpj"] == rpj), {"nombre": rpj})
        f, info = pdf_auditado(rpj, emp["nombre"], anio, tipo, visible=visible)
        ruta, url = Path(f.archivo), f.url
    sofr = None
    try:
        from .datos.tasas_referencia import sofr as _sofr
        sofr = _sofr(anio).valor
    except Exception as e:  # noqa: BLE001
        emitir("aviso", f"Sin SOFR de referencia ({e}); las tasas 'SOFR + margen' quedarán sin convertir.")
    r = extraer(ruta, deuda_esf=d, deuda_esf_anterior=d0, anio=anio, tasa_respaldo=respaldo, sofr=sofr)
    out = r.como_dict()
    out["sofr"] = sofr
    out["kd_pdf"] = {"archivo": str(ruta), "url": url, "pagina": r.pagina, "sofr": sofr,
                     "nota": f"{info.get('documento', '')} {info.get('fecha', '')}".strip()}
    if r.lineas and all(l["tasa_min"] is not None for l in r.lineas):
        out["kd_estimado"] = kd_desde_tabla(lineas_kd(r.lineas))["kd"]
    return out
