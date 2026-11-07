"""Servidor MCP de FinPerú.

Se ejecuta por stdio: el cliente (Claude Desktop, Codex, Antigravity...) lo lanza con
    <carpeta>\\.venv\\Scripts\\python.exe <carpeta>\\mcp_server\\server.py
IMPORTANTE: stdout es del protocolo MCP. Todo mensaje del motor va a stderr (motor/eventos.py).

Las tareas largas (Excel en vivo, navegador) se ejecutan en segundo plano: la herramienta devuelve
un id de trabajo y `consultar_trabajo` espera/reporta el avance. Así ningún cliente se corta por tiempo.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

try:                                            # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Servidor
except ImportError:                             # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Servidor

from motor import __version__, config  # noqa: E402
from motor.datos import damodaran, smv  # noqa: E402
from motor.eventos import suscribir  # noqa: E402
from motor.generar import excel_vivo_disponible, generar_wacc, kd_desde_pdf  # noqa: E402
from motor.industrias import sugerir  # noqa: E402

INSTRUCCIONES = f"""FinPerú v{__version__}: modelos financieros auditables (WACC/CPPC, ROIC y EVA) de empresas peruanas
supervisadas por la SMV, con la metodología del curso Administración Financiera II (UNSAAC).

Flujo recomendado:
1. buscar_empresa("Laive") → obtén el RPJ.
2. vista_previa(rpj, anio) → cifras clave de la SMV (¿cuadra el balance? ¿consolidado o individual?).
3. generar_modelo_wacc(rpj, anio) → devuelve un id; luego consultar_trabajo(id) hasta que termine.
   - industria: si no se da, se sugiere por el CIIU. Lista completa: industrias_damodaran().
   - kd_modo: "pdf" (lee la nota de deuda del PDF auditado; método del curso) o "aproximado".
   - Visualización: ver_excel (Excel celda por celda), ver_navegador (recorrido por SMV, Damodaran,
     Tesoro y BCRP descargando todo), ver_calculos (cada fórmula en Python), velocidad (0 a 3).
4. Comunica WACC, Ke, ROIC, EVA, los controles y TODOS los avisos. No inventes cifras: cita la hoja Fuentes.
Datos del docente (p. ej. inflación) van en `sobrescribir` y quedan marcados como supuestos del usuario.
"""

mcp = _Servidor(name="finperu", instructions=INSTRUCCIONES)

# ------------------------------------------------------------------ trabajos en segundo plano
_TRABAJOS: dict[str, dict] = {}
_bloqueo = threading.Lock()


def _nuevo_trabajo(tipo: str, fn, **kw) -> dict:
    if _bloqueo.locked():
        return {"error": "Ya hay un trabajo en curso. Usa consultar_trabajo para seguirlo."}
    _bloqueo.acquire()
    id_ = uuid.uuid4().hex[:8]
    t = {"id": id_, "tipo": tipo, "estado": "trabajando", "inicio": datetime.now().isoformat(timespec="seconds"),
         "eventos": []}
    _TRABAJOS[id_] = t
    oyente = lambda ev: t["eventos"].append(f"{ev['t'][11:19]} {ev['msg']}")  # noqa: E731
    suscribir(oyente)

    def correr():
        try:
            t["resultado"] = fn(**kw)
            t["estado"] = "listo"
        except Exception as e:  # noqa: BLE001
            t.update(estado="error", error=str(e), detalle=traceback.format_exc(limit=3))
        finally:
            t["fin"] = datetime.now().isoformat(timespec="seconds")
            from motor.eventos import desuscribir
            desuscribir(oyente)
            _bloqueo.release()

    threading.Thread(target=correr, daemon=True).start()
    return {"id": id_, "estado": "trabajando",
            "siguiente": f"Llama consultar_trabajo('{id_}') para ver el avance y el resultado."}


def _resumen_resultado(res: dict) -> dict:
    x = res["resultados"]
    return {"excel": res["excel"], "carpeta": res["carpeta"], "modo": res["modo"], "segundos": res["segundos"],
            "WACC": f"{x['wacc']:.4%}", "Ke": f"{x['ke']:.4%}", "Kd": f"{x['kd']:.4%}", "beta_apalancada": round(x["beta_l"], 4),
            "Wd": f"{x['Wd']:.2%}", "We": f"{x['We']:.2%}", "ROIC": f"{x['roic']:.4%}",
            "EVA_miles_soles": round(x["eva"], 2), "NOPAT": round(x["nopat"], 2),
            "controles": [f"{'OK' if c['ok'] else 'REVISAR'} · {c['control']} ({c['detalle']})" for c in res["controles"]],
            "avisos": res["avisos"], "verificacion_excel": res.get("verificacion_excel")}


# ------------------------------------------------------------------ herramientas
@mcp.tool()
def buscar_empresa(texto: str) -> list[dict]:
    """Busca empresas supervisadas por la SMV por nombre, RUC o código RPJ. Devuelve RPJ, RUC, nombre,
    sector, CIIU, periodos con información y la industria Damodaran sugerida."""
    return [{"rpj": e["rpj"], "ruc": e["ruc"], "nombre": e["nombre"], "sector": e["sector"], "ciiu": e["ciiu"],
             "periodos": f"{e['primer_periodo']} a {e['ultimo_periodo']}", "industria_sugerida": sugerir(e["ciiu"])}
            for e in smv.buscar_empresa(texto, 8)]


@mcp.tool()
def industrias_damodaran(region: str = "emerg") -> list[str]:
    """Lista de industrias de Damodaran (region: emerg | us | global) para elegir la beta comparable."""
    return damodaran.industrias(region)


@mcp.tool()
def vista_previa(rpj: str, anio: int) -> dict:
    """Cifras clave de los estados financieros SMV (miles de S/) del año y del anterior, y si el balance cuadra."""
    df, f, tipo = smv.estados(rpj, anio, via=config.VIA_SMV)
    c, c0 = smv.conceptos(df), smv.conceptos(df, comparativo=True)
    d = lambda k: (k["otros_pasivos_financieros_cp"] or 0) + (k["otros_pasivos_financieros_lp"] or 0)  # noqa: E731
    return {"tipo_estados": "consolidado" if tipo == "C" else "individual", "fuente": f.url,
            str(anio): c, str(anio - 1): c0, "deuda_financiera": d(c),
            "balance_cuadra": abs((c["activo_total"] or 0) - (c["pasivo_total"] or 0) - (c["patrimonio_total"] or 0)) <= 1}


@mcp.tool()
def leer_nota_deuda(rpj: str, anio: int, mostrar_navegador: bool = False) -> dict:
    """Busca el PDF de los EEFF auditados en la SMV y lee la nota de deuda ('otros pasivos financieros'):
    tabla por banco con tasas y saldos, y si cuadra con la deuda del balance. Sirve para revisar el Kd."""
    r = kd_desde_pdf(rpj, anio, visible=mostrar_navegador, via_smv=config.VIA_SMV)
    return {k: r.get(k) for k in ("encontrada", "pagina", "lineas", "total_extraido", "deuda_esf", "cuadra",
                                  "avisos", "kd_estimado", "kd_pdf")}


@mcp.tool()
def generar_modelo_wacc(rpj: str, anio: int, industria: str | None = None, kd_modo: str = "pdf",
                        kd_tabla: list[dict] | None = None, kd: float | None = None,
                        ver_excel: bool = True, ver_navegador: bool = False, ver_calculos: bool = False,
                        velocidad: float = 1.0, parametros: dict[str, Any] | None = None,
                        sobrescribir: dict[str, float] | None = None) -> dict:
    """Construye el Excel auditable de WACC + ROIC + EVA (10 hojas, con fuentes y controles).
    Se ejecuta en segundo plano: devuelve un id; usa consultar_trabajo(id).

    kd_modo: "pdf" (nota de deuda del PDF auditado) | "aproximado" | usa kd_tabla o kd para darlo tú.
    Tasas en decimal (0.0525 = 5.25%). parametros: tasa_impuesto, damodaran_vintage, beta_columna,
    prima_promedio, region_beta. sobrescribir: inflacion_pe, inflacion_us, riesgo_pais, rf, prima, beta_u."""
    if industria is None:
        emp = next((e for e in smv.buscar_empresa(rpj) if e["rpj"] == rpj), {})
        industria = sugerir(emp.get("ciiu")) or "Food Processing"
    kd_arg: Any = kd_tabla or kd
    if kd_arg is None and kd_modo == "pdf":
        kd_arg = "pdf"
    modo = "vivo" if (ver_excel and excel_vivo_disponible()) else "archivo"
    return _nuevo_trabajo("wacc", lambda **k: _resumen_resultado(generar_wacc(**k)),
                          rpj=rpj, anio=anio, industria=industria, kd=kd_arg, parametros=parametros,
                          sobrescribir=sobrescribir, modo=modo, velocidad=velocidad,
                          ver_navegador=ver_navegador, ver_calculos=ver_calculos, via_smv=config.VIA_SMV)


@mcp.tool()
def consultar_trabajo(id: str, esperar_segundos: int = 45) -> dict:
    """Estado de un trabajo. Espera hasta `esperar_segundos` a que termine y devuelve el avance reciente
    y, al terminar, el resultado (WACC, Ke, ROIC, EVA, controles, avisos y ruta del Excel)."""
    t = _TRABAJOS.get(id)
    if not t:
        return {"error": f"No existe el trabajo {id}"}
    fin = time.time() + max(0, min(esperar_segundos, 110))
    while t["estado"] == "trabajando" and time.time() < fin:
        time.sleep(1)
    out = {k: v for k, v in t.items() if k != "eventos"}
    out["avance"] = t["eventos"][-15:]
    return out


@mcp.tool()
def listar_modelos(limite: int = 15) -> list[dict]:
    """Modelos generados (más recientes primero) con WACC, EVA y si pasaron los controles."""
    out = []
    for d in sorted(config.SALIDAS.glob("*/resultados.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limite]:
        try:
            r = json.loads(d.read_text(encoding="utf-8"))
            out.append({"carpeta": str(d.parent), "excel": r.get("excel"), "WACC": r["resultados"]["wacc"],
                        "EVA": r["resultados"]["eva"], "controles_ok": all(c["ok"] for c in r["controles"])})
        except Exception:  # noqa: BLE001
            continue
    return out


@mcp.tool()
def abrir_panel() -> dict:
    """Abre el panel web local de FinPerú (http://127.0.0.1:8765) en el navegador."""
    url = "http://127.0.0.1:8765"
    with socket.socket() as s:
        libre = s.connect_ex(("127.0.0.1", 8765)) != 0
    if libre:
        subprocess.Popen([sys.executable, str(RAIZ / "scripts" / "panel.py")], cwd=str(RAIZ),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    else:
        import webbrowser
        webbrowser.open(url)
    return {"url": url, "iniciado": libre}


@mcp.resource("finperu://metodologia")
def metodologia() -> str:
    """Reglas de cálculo del curso (fuentes, fórmulas, controles y casos de validación)."""
    for p in (RAIZ / "docs" / "metodologia_curso.yaml", RAIZ / "_analisis" / "metodologia_curso.yaml"):
        if p.exists():
            return p.read_text(encoding="utf-8")
    return "No se encontró docs/metodologia_curso.yaml"


@mcp.prompt()
def wacc_de_empresa(empresa: str, anio: str) -> str:
    """Pide el WACC y EVA de una empresa peruana siguiendo el flujo recomendado."""
    return (f"Calcula el WACC, ROIC y EVA de {empresa} para {anio} con FinPerú: busca la empresa, revisa la vista "
            f"previa, genera el modelo con kd_modo='pdf' y ver_excel=True, espera el resultado y explícame cada "
            f"componente (Rf, prima, beta, riesgo país, Kd, pesos), los controles y los avisos.")


def main():
    mcp.run("stdio")


if __name__ == "__main__":
    main()
