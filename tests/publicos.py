"""Archivos públicos usados por las pruebas.

Se buscan primero en tests/fixtures (incluidos en el repositorio: PDF auditados publicados por la SMV,
hojas de Damodaran y el CSV del Tesoro de EE.UU.) y, si no están, en plantillas/_fuente_curso.
"""
from pathlib import Path

from motor import config

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def ruta(nombre: str) -> Path:
    p = FIXTURES / nombre
    return p if p.exists() else config.FUENTE_CURSO / nombre
