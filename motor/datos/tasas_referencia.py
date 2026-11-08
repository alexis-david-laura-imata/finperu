"""Tasas de referencia para deudas a tasa variable ("SOFR + 1.35%").

SOFR (Secured Overnight Financing Rate), Banco de la Reserva Federal de Nueva York, API pública:
  https://markets.newyorkfed.org/api/rates/secured/sofr/search.json?startDate=AAAA-12-15&endDate=AAAA-12-31
Se usa el último dato publicado del año evaluado (cierre), igual que el Rf y el riesgo país.
Si no hay conexión, se usa una tabla de respaldo con los cierres ya verificados (y se avisa).
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import config
from ..eventos import emitir
from .red import Dato, Fuente, descargar

API = "https://markets.newyorkfed.org/api/rates/secured/sofr/search.json?startDate={a}-12-15&endDate={a}-12-31"
# Cierres verificados (NY Fed, vía sofrrate.com): 31/12/2025 = 3.87 %; 31/12/2024 = 4.49 %
RESPALDO = {2024: 0.0449, 2025: 0.0387}


def sofr(anio: int) -> Dato:
    destino = config.CACHE / "tasas" / f"sofr_{anio}.json"
    try:
        f = descargar(API.format(a=anio), destino, "nyfed", max_edad_horas=None if anio < 2026 else 24,
                      nota=f"SOFR diciembre {anio} (NY Fed)")
        datos = json.loads(Path(f.archivo).read_text(encoding="utf-8"))
        obs = sorted(datos.get("refRates", []), key=lambda x: x["effectiveDate"])
        ult = obs[-1]
        v = float(ult["percentRate"]) / 100
        emitir("tasas", f"SOFR al {ult['effectiveDate']} = {v:.2%}")
        return Dato(v, f, detalle=f"SOFR NY Fed al {ult['effectiveDate']} (último dato de {anio}) = {v:.2%}")
    except Exception as e:  # noqa: BLE001
        if anio in RESPALDO:
            emitir("aviso", f"No pude consultar SOFR en la NY Fed ({e}); uso el cierre verificado {RESPALDO[anio]:.2%}")
            return Dato(RESPALDO[anio], Fuente(url="https://www.newyorkfed.org/markets/reference-rates/sofr",
                                               archivo="", sha256="-", descargado="", origen="nyfed",
                                               nota="tabla de respaldo FinPerú"),
                        detalle=f"SOFR cierre {anio} = {RESPALDO[anio]:.2%} (tabla de respaldo verificada)")
        raise
