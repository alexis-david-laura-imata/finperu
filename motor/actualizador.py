"""Actualizaciones automáticas desde GitHub (github.com/alexis-david-laura-imata/finperu).

Cómo funciona:
1. Consulta la última *release* publicada (API pública de GitHub, sin contraseña).
   Si aún no hay releases, compara con el archivo VERSION de la rama main.
2. Si hay una versión más nueva, descarga el .zip, reemplaza SOLO las carpetas de código
   y conserva intactos los datos del usuario.
3. Sincroniza las dependencias (uv o pip) y vuelve a registrar el MCP (las rutas no cambian).

Nunca se tocan: .venv, datos_cache, salidas, plantillas/_fuente_curso, _analisis, config.local.json.
Antes de reemplazar, guarda una copia del código actual en datos_cache/respaldos/<versión>/.
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import requests

from . import REPOSITORIO, __version__
from .eventos import emitir

RAIZ = Path(__file__).resolve().parents[1]
API = f"https://api.github.com/repos/{REPOSITORIO}"
RAW_VERSION = f"https://raw.githubusercontent.com/{REPOSITORIO}/main/VERSION"
ZIP_MAIN = f"https://github.com/{REPOSITORIO}/archive/refs/heads/main.zip"
CARPETAS_CODIGO = ["motor", "mcp_server", "web", "scripts", "tests", "docs", "instalador", ".github"]
ARCHIVOS_RAIZ = ["VERSION", "requirements.txt", "README.md", "CHANGELOG.md", "LICENSE", ".gitignore",
                 "FinPeru.bat", "Instalar FinPeru.bat", "Actualizar FinPeru.bat", "Iniciar FinPeru.bat"]
INTOCABLES = {".venv", "datos_cache", "salidas", "_analisis", "config.local.json"}
CABECERAS = {"User-Agent": "FinPeru-actualizador", "Accept": "application/vnd.github+json"}


def _tupla(v: str) -> tuple:
    return tuple(int(x) for x in v.strip().lstrip("vV").split(".") if x.isdigit())


def consultar() -> dict:
    """{'actual', 'ultima', 'hay_actualizacion', 'notas', 'zip'}; nunca lanza excepción."""
    info = {"actual": __version__, "ultima": None, "hay_actualizacion": False, "notas": "", "zip": None}
    try:
        r = requests.get(f"{API}/releases/latest", headers=CABECERAS, timeout=15)
        if r.status_code == 200:
            rel = r.json()
            info["ultima"] = rel["tag_name"].lstrip("v")
            info["notas"] = rel.get("body") or ""
            asset = next((a for a in rel.get("assets", []) if a["name"].lower().endswith(".zip")), None)
            info["zip"] = asset["browser_download_url"] if asset else rel["zipball_url"]
        else:
            r = requests.get(RAW_VERSION, timeout=15)
            if r.status_code == 200:
                info["ultima"], info["zip"] = r.text.strip(), ZIP_MAIN
        if info["ultima"]:
            info["hay_actualizacion"] = _tupla(info["ultima"]) > _tupla(__version__)
    except requests.RequestException as e:
        info["error"] = f"Sin conexión con GitHub: {e}"
    return info


def _raiz_del_zip(z: zipfile.ZipFile) -> str:
    """Los zip de GitHub traen una carpeta raíz (finperu-main/...); el nuestro puede o no traerla."""
    nombres = z.namelist()
    if any(n == "VERSION" for n in nombres):
        return ""
    candidatos = {n.split("/")[0] + "/" for n in nombres if "/" in n}
    for c in candidatos:
        if c + "VERSION" in nombres:
            return c
    raise ValueError("El paquete descargado no parece ser FinPerú (no tiene VERSION).")


def aplicar(url_zip: str | None = None, sincronizar_dependencias: bool = True) -> dict:
    info = consultar() if not url_zip else {"zip": url_zip, "ultima": "?"}
    if not info.get("zip"):
        return {"ok": False, "mensaje": info.get("error", "No hay versión publicada en GitHub todavía.")}
    if url_zip is None and not info.get("hay_actualizacion"):
        return {"ok": True, "mensaje": f"Ya tienes la última versión ({__version__})."}
    emitir("actualizar", f"Descargando FinPerú {info['ultima']}…")
    if Path(str(info["zip"])).exists():                     # instalación desde un .zip local
        contenido = Path(info["zip"]).read_bytes()
    else:
        r = requests.get(info["zip"], headers={"User-Agent": CABECERAS["User-Agent"]}, timeout=300)
        r.raise_for_status()
        contenido = r.content
    z = zipfile.ZipFile(io.BytesIO(contenido))
    base = _raiz_del_zip(z)

    respaldo = RAIZ / "datos_cache" / "respaldos" / f"{__version__}_{datetime.now():%Y%m%d-%H%M%S}"
    respaldo.mkdir(parents=True, exist_ok=True)
    for c in CARPETAS_CODIGO:
        if (RAIZ / c).exists():
            shutil.copytree(RAIZ / c, respaldo / c, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "bin"))
    for a in ARCHIVOS_RAIZ:
        if (RAIZ / a).exists():
            shutil.copy2(RAIZ / a, respaldo / a)
    emitir("actualizar", f"Copia de seguridad del código actual en {respaldo}")

    nuevos = {n[len(base):]: n for n in z.namelist() if n.startswith(base) and not n.endswith("/")}
    for c in CARPETAS_CODIGO:                              # reemplazo limpio de carpetas de código
        if any(k.startswith(c + "/") for k in nuevos) and (RAIZ / c).exists():
            for hijo in (RAIZ / c).iterdir():
                if hijo.name in ("bin",):                  # uv.exe del instalador se conserva
                    continue
                shutil.rmtree(hijo) if hijo.is_dir() else hijo.unlink()
    escritos = 0
    for rel, nombre in nuevos.items():
        primera = rel.split("/")[0]
        if primera in INTOCABLES or rel.startswith("plantillas/_fuente_curso"):
            continue
        destino = RAIZ / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(z.read(nombre))
        escritos += 1
    emitir("actualizar", f"{escritos} archivos actualizados")

    if sincronizar_dependencias:
        sincronizar()
    try:
        subprocess.run([sys.executable, str(RAIZ / "scripts" / "registrar_mcp.py")], cwd=RAIZ, timeout=60,
                       capture_output=True)
    except Exception:  # noqa: BLE001
        pass
    nueva = (RAIZ / "VERSION").read_text(encoding="utf-8").strip()
    emitir("actualizar", f"FinPerú actualizado a {nueva}. Reinicia el panel y los asistentes.")
    return {"ok": True, "mensaje": f"Actualizado de {__version__} a {nueva}. Reinicia FinPerú.",
            "version": nueva, "respaldo": str(respaldo), "notas": info.get("notas", "")}


def sincronizar() -> None:
    uv = RAIZ / "instalador" / "bin" / "uv.exe"
    req = str(RAIZ / "requirements.txt")
    if uv.exists():
        cmd = [str(uv), "pip", "install", "--python", sys.executable, "-r", req]
    else:
        cmd = [sys.executable, "-m", "pip", "install", "-q", "-r", req]
    emitir("actualizar", "Sincronizando dependencias…")
    subprocess.run(cmd, cwd=RAIZ, timeout=1800)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Actualiza FinPerú desde GitHub")
    ap.add_argument("--solo-consultar", action="store_true")
    ap.add_argument("--zip", help="instalar desde un .zip/URL específico")
    a = ap.parse_args()
    if a.solo_consultar:
        print(json.dumps(consultar(), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(aplicar(a.zip), ensure_ascii=False, indent=1))
