"""Bus de eventos del motor: cada paso (descarga, celda escrita, control) emite un evento.

- Se imprime en consola.
- Se agrega a datos_cache/eventos.jsonl (la web localhost lo lee en vivo).
- Se puede enganchar un oyente extra (p.ej. el servidor web con SSE).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Callable

from . import config

_oyentes: list[Callable[[dict], None]] = []
ARCHIVO = config.CACHE / "eventos.jsonl"
SILENCIO = False


def suscribir(fn: Callable[[dict], None]) -> None:
    _oyentes.append(fn)


def desuscribir(fn: Callable[[dict], None]) -> None:
    if fn in _oyentes:
        _oyentes.remove(fn)


def emitir(tipo: str, mensaje: str, **datos) -> dict:
    ev = {"t": datetime.now().isoformat(timespec="milliseconds"), "tipo": tipo, "msg": mensaje, "pid": os.getpid(), **datos}
    if not SILENCIO:
        print(f"[{ev['t'][11:19]}] {tipo:<12} {mensaje}", file=sys.stderr)
    try:
        with open(ARCHIVO, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass
    for fn in list(_oyentes):
        try:
            fn(ev)
        except Exception:  # un oyente roto nunca debe tumbar el motor
            pass
    return ev
