"""Rutas y parámetros globales del motor FinPerú.

Todas las rutas se resuelven respecto a la carpeta del proyecto ("MCP financiero"),
así el mismo código funciona en Windows y en cualquier otra máquina.
"""
from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(os.environ.get("FINPERU_RAIZ", Path(__file__).resolve().parents[1]))
CACHE = RAIZ / "datos_cache"
SALIDAS = RAIZ / "salidas"
PLANTILLAS = RAIZ / "plantillas"
FUENTE_CURSO = PLANTILLAS / "_fuente_curso"
REGISTRO_FUENTES = CACHE / "registro_fuentes.jsonl"

for _p in (CACHE, SALIDAS):
    _p.mkdir(parents=True, exist_ok=True)

# Vía por defecto para la SMV: auto (en vivo y si falla, espejo) | smv | espejo
VIA_SMV = os.environ.get("FINPERU_VIA_SMV", "auto")

from . import __version__ as _v
USER_AGENT = f"FinPeru/{_v} (+https://github.com/alexis-david-laura-imata/finperu)"

# Parámetros metodológicos por defecto (ver _analisis/metodologia_curso.yaml)
PARAMETROS_DEFECTO = {
    "tasa_impuesto": 0.295,
    "damodaran_vintage": "cierre_siguiente",   # o "disponible_al_cierre"
    "beta_columna": "Unlevered beta",          # o "Unlevered beta corrected for cash"
    "prima_promedio": "aritmetico",            # o "geometrico"
    "region_beta": "emerg",                    # emerg | us | global
    "estados_tipo": "C",                       # C consolidado, cae a I individual si no hay
}
