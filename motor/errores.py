"""Mensajes de error comprensibles para el usuario (panel, MCP y consola)."""
from __future__ import annotations

import traceback

from .eventos import emitir

INSTALAR = "Cierra FinPerú y ábrelo con FinPeru.bat (instala lo que falte) o ejecuta 'Instalar FinPeru.bat'."


def falta_modulo(e: BaseException) -> str | None:
    if isinstance(e, ModuleNotFoundError):
        return f"Falta la librería '{e.name}' en el entorno de FinPerú. {INSTALAR}"
    return None


def mensaje(e: BaseException) -> str:
    """Texto para mostrar. Los errores internos inesperados incluyen el tipo para poder diagnosticarlos."""
    from .metodologia import DatosIncompletos
    if (m := falta_modulo(e)):
        return m
    if isinstance(e, (DatosIncompletos, LookupError)):
        return str(e)
    return f"{type(e).__name__}: {e}"


def registrar(e: BaseException, contexto: str = "") -> str:
    """Emite un evento 'error' con el detalle técnico (queda en datos_cache/eventos.jsonl) y devuelve el mensaje."""
    msg = mensaje(e)
    emitir("error", f"{contexto}{msg}", detalle=traceback.format_exc(limit=6))
    return msg
