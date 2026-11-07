"""Registra (o quita) el servidor MCP de FinPerú en Claude Desktop, Codex y Antigravity.

    python scripts\\registrar_mcp.py              # registra en todos los que encuentre
    python scripts\\registrar_mcp.py --quitar     # lo quita de todos
    python scripts\\registrar_mcp.py --solo codex

- Antes de modificar un archivo de configuración guarda una copia: <archivo>.finperu-respaldo-AAAAMMDD-HHMMSS
- Es idempotente: ejecutarlo varias veces no duplica nada.
- Después de registrar, reinicia el asistente (ciérralo por completo y ábrelo de nuevo).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
NOMBRE = "finperu"


def python_finperu() -> Path:
    for p in (RAIZ / ".venv" / "Scripts" / "python.exe", RAIZ / ".venv" / "bin" / "python"):
        if p.exists():
            return p
    return Path(sys.executable)


def entrada() -> dict:
    return {"command": str(python_finperu()), "args": [str(RAIZ / "mcp_server" / "server.py")],
            "env": {"PYTHONIOENCODING": "utf-8"}}


def respaldo(archivo: Path) -> None:
    if archivo.exists():
        destino = archivo.with_name(f"{archivo.name}.finperu-respaldo-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(archivo, destino)


# ------------------------------------------------------------------ JSON (Claude Desktop, Antigravity)
def _json(archivo: Path, quitar: bool) -> str:
    datos = {}
    if archivo.exists():
        texto = archivo.read_text(encoding="utf-8-sig").strip()
        datos = json.loads(texto) if texto else {}
    servidores = datos.setdefault("mcpServers", {})
    if quitar:
        if NOMBRE not in servidores:
            return "no estaba registrado"
        respaldo(archivo)
        servidores.pop(NOMBRE)
    else:
        if servidores.get(NOMBRE) == entrada():
            return "ya estaba registrado (sin cambios)"
        respaldo(archivo)
        servidores[NOMBRE] = entrada()
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return "quitado" if quitar else "registrado"


def rutas_claude() -> list[Path]:
    appdata, local = os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA")
    rutas = []
    if appdata:
        rutas.append(Path(appdata) / "Claude" / "claude_desktop_config.json")
    if local:                                            # instalación desde Microsoft Store / MSIX
        rutas += sorted(Path(local, "Packages").glob("Claude_*/LocalCache/Roaming/Claude/claude_desktop_config.json"))
        rutas += [p / "LocalCache/Roaming/Claude/claude_desktop_config.json"
                  for p in Path(local, "Packages").glob("Claude_*") if p.is_dir()]
    if sys.platform == "darwin":
        rutas.append(Path.home() / "Library/Application Support/Claude/claude_desktop_config.json")
    vistos, out = set(), []
    for r in rutas:
        if r not in vistos and (r.exists() or r.parent.exists()):
            vistos.add(r)
            out.append(r)
    return out


def rutas_antigravity() -> list[Path]:
    base = Path.home() / ".gemini"
    candidatas = [base / "config" / "mcp_config.json",          # Antigravity 2.0 (IDE y CLI)
                  base / "antigravity" / "mcp_config.json"]     # versiones anteriores
    existentes = [p for p in candidatas if p.exists() or p.parent.exists()]
    return existentes or ([candidatas[0]] if base.exists() else [])


# ------------------------------------------------------------------ TOML (Codex)
def _codex(archivo: Path, quitar: bool) -> str:
    texto = archivo.read_text(encoding="utf-8") if archivo.exists() else ""
    patron = re.compile(rf"(?ms)^\[mcp_servers\.{NOMBRE}(\.[^\]]+)?\]\s*\n.*?(?=^\[(?!mcp_servers\.{NOMBRE}\b)|\Z)")
    sin = patron.sub("", texto).rstrip() + ("\n" if texto.strip() else "")
    if quitar:
        if sin == texto:
            return "no estaba registrado"
        respaldo(archivo)
        archivo.write_text(sin, encoding="utf-8")
        return "quitado"
    e = entrada()
    bloque = (f"\n[mcp_servers.{NOMBRE}]\n"
              f"command = {json.dumps(e['command'])}\n"
              f"args = [{', '.join(json.dumps(a) for a in e['args'])}]\n"
              f"startup_timeout_sec = 60\n"
              f"tool_timeout_sec = 300\n\n"
              f"[mcp_servers.{NOMBRE}.env]\n"
              f'PYTHONIOENCODING = "utf-8"\n')
    nuevo = sin + bloque
    if nuevo.strip() == texto.strip():
        return "ya estaba registrado (sin cambios)"
    respaldo(archivo)
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(nuevo, encoding="utf-8")
    return "registrado"


def ruta_codex() -> Path | None:
    base = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return base / "config.toml" if base.exists() else None


# ------------------------------------------------------------------ principal
def registrar(quitar: bool = False, solo: str | None = None) -> list[tuple[str, str, str]]:
    res = []
    if solo in (None, "claude"):
        rs = rutas_claude()
        if not rs:
            res.append(("Claude Desktop", "-", "no encontrado (¿está instalado?)"))
        for r in rs:
            res.append(("Claude Desktop", str(r), _json(r, quitar)))
    if solo in (None, "codex"):
        r = ruta_codex()
        res.append(("Codex", str(r) if r else "-", _codex(r, quitar) if r else "no encontrado (~/.codex)"))
    if solo in (None, "antigravity"):
        rs = rutas_antigravity()
        if not rs:
            res.append(("Antigravity", "-", "no encontrado (~/.gemini)"))
        for r in rs:
            res.append(("Antigravity", str(r), _json(r, quitar)))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Registra FinPerú como servidor MCP")
    ap.add_argument("--quitar", action="store_true")
    ap.add_argument("--solo", choices=["claude", "codex", "antigravity"])
    a = ap.parse_args()
    print(f"Servidor: {entrada()['command']} {entrada()['args'][0]}")
    for cliente, ruta, estado in registrar(a.quitar, a.solo):
        print(f"  {cliente:<15} {estado:<34} {ruta}")
    print("Reinicia los asistentes (ciérralos por completo y ábrelos) para que carguen FinPerú.")
