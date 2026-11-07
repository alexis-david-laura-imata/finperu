"""Arma el paquete distribuible dist/FinPeru-vX.Y.Z.zip.

    python scripts/empaquetar.py            # incluye instalador/bin/uv.exe si existe
    python scripts/empaquetar.py --sin-uv

El zip trae una carpeta raíz "FinPeru/" con solo el código y la documentación: nunca incluye
.venv, datos_cache, salidas, _analisis ni plantillas/_fuente_curso (material privado del curso).
"""
from __future__ import annotations

import argparse
import fnmatch
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
INCLUIR = ["motor", "mcp_server", "web", "scripts", "tests", "docs", "instalador", ".github", "plantillas",
           "VERSION", "requirements.txt", "README.md", "CHANGELOG.md", "LICENSE", ".gitignore",
           "FinPeru.bat", "Instalar FinPeru.bat", "Actualizar FinPeru.bat", "Iniciar FinPeru.bat"]
EXCLUIR = ["*/__pycache__/*", "*.pyc", "*/.pytest_cache/*", "plantillas/_fuente_curso/*",
           "instalador/python/*", "*.finperu-respaldo-*", "*/~$*", "*.log"]


def archivos(con_uv: bool):
    for nombre in INCLUIR:
        p = RAIZ / nombre
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if not f.is_file():
                    continue
                rel = f.relative_to(RAIZ).as_posix()
                if any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch("/" + rel, pat) for pat in EXCLUIR):
                    continue
                if rel.startswith("instalador/bin/") and not con_uv:
                    continue
                yield f


def empaquetar(con_uv: bool = True, destino: Path | None = None) -> Path:
    version = (RAIZ / "VERSION").read_text(encoding="utf-8").strip()
    destino = destino or RAIZ / "dist" / f"FinPeru-v{version}.zip"
    destino.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in archivos(con_uv):
            z.write(f, "FinPeru/" + f.relative_to(RAIZ).as_posix())
            n += 1
    print(f"{destino}  ({n} archivos, {destino.stat().st_size / 1e6:.1f} MB)")
    return destino


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sin-uv", action="store_true")
    ap.add_argument("--salida")
    a = ap.parse_args()
    empaquetar(not a.sin_uv, Path(a.salida) if a.salida else None)
