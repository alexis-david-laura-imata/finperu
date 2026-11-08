"""Panel web local de FinPerú (http://127.0.0.1:8765).

Capa delgada sobre el motor: no contiene lógica financiera. La interfaz (web/static) solo
habla con estas rutas, documentadas en web/README.md. Puedes rediseñar la interfaz sin tocar esto.

Solo escucha en 127.0.0.1 (tu PC). No es accesible desde otras computadoras.
"""
from __future__ import annotations

import json
import re
import os
import platform
import subprocess
import threading
import traceback
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from motor import __version__, config
from motor.datos import damodaran, smv
from motor.eventos import suscribir
from motor.generar import excel_vivo_disponible, generar_wacc, kd_desde_pdf
from motor.industrias import sugerir

app = FastAPI(title="FinPerú — panel local", version=__version__)
ESTATICOS = Path(__file__).parent / "static"

# ------------------------------------------------------------------ eventos en vivo (SSE)
_EVENTOS: deque = deque(maxlen=3000)
_contador = 0
_lock_ev = threading.Lock()


def _recibir(ev: dict) -> None:
    global _contador
    with _lock_ev:
        _contador += 1
        _EVENTOS.append({"id": _contador, **ev})


suscribir(_recibir)


def _seguir_otros_procesos() -> None:
    """Muestra en el panel los eventos de otros procesos (servidor MCP, demo) leyendo eventos.jsonl."""
    import os
    import time as _t
    from motor.eventos import ARCHIVO
    pos = ARCHIVO.stat().st_size if ARCHIVO.exists() else 0
    while True:
        try:
            if ARCHIVO.exists():
                tam = ARCHIVO.stat().st_size
                if tam < pos:
                    pos = 0
                if tam > pos:
                    with open(ARCHIVO, encoding="utf-8") as f:
                        f.seek(pos)
                        for linea in f:
                            try:
                                ev = json.loads(linea)
                            except ValueError:
                                continue
                            if ev.get("pid") != os.getpid():
                                _recibir({**ev, "externo": True})
                        pos = f.tell()
        except OSError:
            pass
        _t.sleep(0.4)


threading.Thread(target=_seguir_otros_procesos, daemon=True).start()

# ------------------------------------------------------------------ trabajos (uno a la vez)
_TRABAJOS: dict[str, dict] = {}
_lock_trabajo = threading.Lock()


class LineaKd(BaseModel):
    tipo: str = "PRESTAMOS BANCARIOS"
    entidad: str = ""
    tasa_min: float = Field(..., description="Decimal: 0.0525 = 5.25%")
    tasa_max: float | None = None
    corriente: float = 0
    no_corriente: float = 0
    moneda: str = "S/"
    nota: str = ""


class PedidoGenerar(BaseModel):
    rpj: str
    anio: int
    industria: str
    plantilla: str = "wacc"
    modo: str = Field("auto", description="vivo | archivo | auto")
    velocidad: float = 1.0
    kd_tabla: list[LineaKd] | None = None
    kd: float | None = Field(None, description="Kd único (si no hay tabla)")
    kd_modo: str = Field("aproximado", description="aproximado | pdf | tabla | unico")
    ver_navegador: bool = Field(False, description="ver el navegador recorrer y descargar las fuentes")
    ver_calculos: bool = Field(False, description="ver cada cálculo en Python con su fórmula")
    parametros: dict[str, Any] | None = None
    sobrescribir: dict[str, float] | None = None
    via_smv: str | None = None
    kd_pdf: dict[str, Any] | None = Field(None, description="Procedencia de la tabla Kd (lo devuelve /api/kd_pdf)")


def _ejecutar(id_: str, p: PedidoGenerar) -> None:
    t = _TRABAJOS[id_]
    try:
        kd = [x.model_dump() for x in p.kd_tabla] if p.kd_tabla else p.kd
        if p.kd_modo == "pdf" and not p.kd_tabla:
            kd = "pdf"
        res = generar_wacc(p.rpj, p.anio, p.industria, kd=kd, parametros=p.parametros,
                           sobrescribir=p.sobrescribir or None, modo=p.modo, velocidad=p.velocidad,
                           ver_navegador=p.ver_navegador, ver_calculos=p.ver_calculos,
                           via_smv=p.via_smv or config.VIA_SMV, kd_pdf=p.kd_pdf)
        t.update(estado="listo", resultado=res)
    except Exception as e:  # noqa: BLE001
        from motor.errores import registrar
        t.update(estado="error", error=registrar(e), detalle=traceback.format_exc(limit=6))
    finally:
        t["fin"] = datetime.now().isoformat(timespec="seconds")
        _lock_trabajo.release()


# ------------------------------------------------------------------ rutas API
@app.get("/api/estado")
def estado():
    return {"version": __version__, "excel_vivo": excel_vivo_disponible(), "sistema": platform.system(),
            "salidas": str(config.SALIDAS), "ocupado": _lock_trabajo.locked()}


@app.get("/api/empresas")
def empresas(q: str, limite: int = 10):
    if len(q.strip()) < 2:
        return []
    out = []
    for e in smv.buscar_empresa(q, limite):
        out.append({"rpj": e["rpj"], "ruc": e["ruc"], "nombre": e["nombre"], "ciiu": e["ciiu"],
                    "sector": e["sector"], "tipo_empresa": e["tipo_empresa"],
                    "primer_periodo": e["primer_periodo"], "ultimo_periodo": e["ultimo_periodo"],
                    "industria_sugerida": sugerir(e["ciiu"])})
    return out


@app.get("/api/industrias")
def industrias(region: str = "emerg"):
    try:
        return damodaran.industrias(region)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"No se pudo leer la lista de Damodaran: {e}")


@app.get("/api/vista_previa")
def vista_previa(rpj: str, anio: int, via: str | None = None):
    """Cifras clave de la SMV antes de generar (para revisar y para cuadrar la tabla de Kd)."""
    try:
        df, f, tipo = smv.estados(rpj, anio, via=via or config.VIA_SMV)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(404, str(e))
    c, c0 = smv.conceptos(df), smv.conceptos(df, comparativo=True)
    d = lambda k: (k["otros_pasivos_financieros_cp"] or 0) + (k["otros_pasivos_financieros_lp"] or 0)  # noqa: E731
    return {"rpj": rpj, "anio": anio, "tipo_estados": tipo, "fuente": f.url, "conceptos": c,
            "conceptos_anterior": c0, "deuda_financiera": d(c), "deuda_financiera_anterior": d(c0),
            "cuadra": abs((c["activo_total"] or 0) - (c["pasivo_total"] or 0) - (c["patrimonio_total"] or 0)) <= 1}


class PedidoKdPdf(BaseModel):
    rpj: str
    anio: int
    visible: bool = True


@app.post("/api/kd_pdf")
def kd_pdf(p: PedidoKdPdf):
    """Busca el PDF auditado en la SMV (navegador visible opcional) y lee la nota de deuda."""
    try:
        return kd_desde_pdf(p.rpj, p.anio, visible=p.visible, via_smv=config.VIA_SMV)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, f"No se pudo leer la nota de deuda: {e}")


@app.post("/api/kd_pdf_subir")
async def kd_pdf_subir(rpj: str = Form(...), anio: int = Form(...), archivo: UploadFile = File(...)):
    """Lee la nota de deuda de un PDF que sube el usuario."""
    carpeta = config.CACHE / "smv" / "pdf" / "subidos"
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = re.sub(r"[^A-Za-z0-9._-]+", "_", archivo.filename or "eeff.pdf")
    ruta = carpeta / f"{rpj}_{anio}_{nombre}"
    contenido = await archivo.read()
    if not contenido.startswith(b"%PDF"):
        raise HTTPException(400, "El archivo no es un PDF.")
    ruta.write_bytes(contenido)
    try:
        return kd_desde_pdf(rpj, anio, archivo_pdf=ruta, via_smv=config.VIA_SMV)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, f"No se pudo leer la nota de deuda: {e}")


@app.post("/api/generar", status_code=202)
def generar(p: PedidoGenerar):
    if p.plantilla != "wacc":
        raise HTTPException(400, "Por ahora solo está disponible la plantilla 'wacc'.")
    if not _lock_trabajo.acquire(blocking=False):
        raise HTTPException(409, "Ya hay un modelo construyéndose. Espera a que termine.")
    id_ = uuid.uuid4().hex[:10]
    _TRABAJOS[id_] = {"id": id_, "estado": "trabajando", "inicio": datetime.now().isoformat(timespec="seconds"),
                      "pedido": p.model_dump()}
    threading.Thread(target=_ejecutar, args=(id_, p), daemon=True).start()
    return {"id": id_}


@app.get("/api/trabajos/{id_}")
def trabajo(id_: str):
    if id_ not in _TRABAJOS:
        raise HTTPException(404, "Trabajo no encontrado")
    return _TRABAJOS[id_]


@app.get("/api/eventos")
async def eventos(desde: int = 0):
    """Server-Sent Events: cada evento del motor (descargas, pasos de Excel, controles)."""
    import asyncio

    async def flujo():
        ultimo = desde or _contador
        while True:
            with _lock_ev:
                nuevos = [e for e in _EVENTOS if e["id"] > ultimo]
            for e in nuevos:
                ultimo = e["id"]
                yield f"id: {e['id']}\ndata: {json.dumps(e, ensure_ascii=False, default=str)}\n\n"
            if not nuevos:
                yield ": latido\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(flujo(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _carpeta_segura(nombre: str) -> Path:
    p = (config.SALIDAS / nombre).resolve()
    if config.SALIDAS.resolve() not in p.parents or not p.is_dir():
        raise HTTPException(404, "Modelo no encontrado")
    return p


@app.get("/api/historial")
def historial(limite: int = 30):
    out = []
    for d in sorted(config.SALIDAS.glob("*/resultados.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limite]:
        try:
            r = json.loads(d.read_text(encoding="utf-8"))
            rc = json.loads((d.parent / "receta.json").read_text(encoding="utf-8"))
            out.append({"carpeta": d.parent.name, "empresa": rc.get("empresa"), "anio": rc.get("anio"),
                        "generado": rc.get("generado"), "wacc": r["resultados"]["wacc"],
                        "eva": r["resultados"]["eva"], "modo": r.get("modo"),
                        "controles_ok": all(c["ok"] for c in r.get("controles", []))})
        except Exception:  # noqa: BLE001
            continue
    return out


@app.get("/api/modelos/{carpeta}/excel")
def descargar_excel(carpeta: str):
    p = _carpeta_segura(carpeta)
    x = next(p.glob("*.xlsx"), None)
    if not x:
        raise HTTPException(404, "Excel no encontrado")
    return FileResponse(x, filename=x.name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/api/modelos/{carpeta}/abrir")
def abrir(carpeta: str, que: str = "excel"):
    """Abre el Excel o la carpeta del modelo en tu PC (solo Windows)."""
    p = _carpeta_segura(carpeta)
    objetivo = next(p.glob("*.xlsx"), p) if que == "excel" else p
    if platform.system() == "Windows":
        os.startfile(str(objetivo))  # noqa: S606
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", str(objetivo)])
    else:
        subprocess.Popen(["xdg-open", str(objetivo)])
    return {"abierto": str(objetivo)}


@app.get("/api/actualizacion")
def actualizacion():
    from motor.actualizador import consultar
    return consultar()


@app.post("/api/actualizar")
def actualizar():
    if _lock_trabajo.locked():
        raise HTTPException(409, "Espera a que termine el modelo en curso.")
    from motor.actualizador import aplicar
    try:
        return aplicar()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"No se pudo actualizar: {e}")


# ------------------------------------------------------------------ interfaz
app.mount("/", StaticFiles(directory=ESTATICOS, html=True), name="interfaz")
