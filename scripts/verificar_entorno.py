"""Revisa que el entorno de FinPerú tenga todas las librerías de requirements.txt y, si falta alguna,
la instala (con uv si está en instalador/bin, si no con pip). Lo llama FinPeru.bat al abrir.

    python scripts/verificar_entorno.py            # revisa e instala lo que falte
    python scripts/verificar_entorno.py --solo-revisar
Sale con código 0 si al final todo está bien.
"""
from __future__ import annotations

import hashlib
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REQ = RAIZ / "requirements.txt"
MARCA = Path(sys.prefix) / "finperu_requisitos.sha256"
# nombre en requirements -> módulo que se importa (cuando difieren)
MODULOS = {"python-multipart": "multipart", "pyyaml": "yaml", "pillow": "PIL"}


def requisitos() -> list[str]:
    out = []
    for linea in REQ.read_text(encoding="utf-8").splitlines():
        linea = linea.split("#")[0].strip()
        if not linea:
            continue
        if ";" in linea and "win32" in linea and sys.platform != "win32":
            continue
        out.append(re.split(r"[<>=!~;\[ ]", linea, maxsplit=1)[0].strip())
    return out


def faltantes() -> list[str]:
    return [p for p in requisitos()
            if importlib.util.find_spec(MODULOS.get(p.lower(), p.replace("-", "_"))) is None]


def huella() -> str:
    return hashlib.sha256(REQ.read_bytes()).hexdigest()


def instalar() -> int:
    uv = RAIZ / "instalador" / "bin" / ("uv.exe" if sys.platform == "win32" else "uv")
    cmd = ([str(uv), "pip", "install", "--python", sys.executable, "-r", str(REQ)] if uv.exists()
           else [sys.executable, "-m", "pip", "install", "-r", str(REQ)])
    print("Instalando librerías que faltan:", " ".join(cmd))
    return subprocess.run(cmd, cwd=RAIZ).returncode


def main(solo_revisar: bool = False) -> int:
    al_dia = MARCA.exists() and MARCA.read_text().strip() == huella()
    falta = faltantes()
    if al_dia and not falta:
        return 0
    if solo_revisar:
        if falta:
            print("Faltan librerías:", ", ".join(falta))
        return 1 if falta else 0
    if falta:
        print("Faltan librerías:", ", ".join(falta))
    # requirements.txt cambió (actualización) o falta algo: sincronizar
    if instalar() != 0 or faltantes():
        print("No se pudieron instalar todas las librerías. Ejecuta 'Instalar FinPeru.bat'.")
        return 1
    try:
        MARCA.write_text(huella())
    except OSError:
        pass
    print("Entorno de FinPerú al día.")
    return 0


if __name__ == "__main__":
    sys.exit(main("--solo-revisar" in sys.argv))
