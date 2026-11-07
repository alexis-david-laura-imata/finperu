"""Tasa libre de riesgo: bono del Tesoro de EE.UU. a 10 años (Daily Par Yield Curve).

Regla del curso: rendimiento a 10 años del ÚLTIMO día hábil del año (ej. 29/12/2023 = 3.88%).
CSV por año: https://home.treasury.gov/resource-center/data-chart-center/interest-rates/
             daily-treasury-rates.csv/{AAAA}/all?type=daily_treasury_yield_curve&field_tdr_date_value={AAAA}&page&_format=csv
También acepta el CSV histórico del curso (par-yield-curve-rates-2020-2023.csv).
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path

from .. import config
from ..eventos import emitir
from .red import Dato, descargar, fuente_local

URL = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
       "daily-treasury-rates.csv/{a}/all?type=daily_treasury_yield_curve&field_tdr_date_value={a}&page&_format=csv")
CARPETA = config.CACHE / "tesoro"


def _valida(b: bytes) -> None:
    if b"10 Yr" not in b[:500] and b"10 yr" not in b[:500]:
        raise ValueError("El CSV del Tesoro no trae la columna '10 Yr'")


def _filas(ruta: str) -> list[tuple[datetime, float]]:
    texto = Path(ruta).read_text(encoding="utf-8-sig")
    lector = csv.DictReader(io.StringIO(texto))
    col = next(c for c in lector.fieldnames if c.strip().lower() == "10 yr")
    col_f = next(c for c in lector.fieldnames if c.strip().lower() == "date")
    out = []
    for fila in lector:
        v = (fila.get(col) or "").strip()
        if not v or v.upper() == "N/A":
            continue
        out.append((datetime.strptime(fila[col_f].strip(), "%m/%d/%Y"), float(v)))
    return out


def rf_10y(anio: int, local: Path | None = None) -> Dato:
    if local:
        f = fuente_local(local, "tesoro", url="https://home.treasury.gov/resource-center/data-chart-center/"
                                               "interest-rates/daily-treasury-rate-archives")
    else:
        f = descargar(URL.format(a=anio), CARPETA / f"par_yield_{anio}.csv", "tesoro", validar=_valida,
                      max_edad_horas=None if anio < datetime.now().year else 24)
    filas = [x for x in _filas(f.archivo) if x[0].year == anio]
    if not filas:
        raise LookupError(f"El CSV del Tesoro no tiene datos de {anio}")
    fecha, v = max(filas, key=lambda x: x[0])
    emitir("tesoro", f"Rf 10 años al {fecha:%d/%m/%Y} = {v:.2f}%")
    return Dato(v / 100, f, detalle=f"Tesoro EE.UU., Daily Par Yield Curve, '10 Yr' al {fecha:%d/%m/%Y} "
                                    f"(último día hábil de {anio}) = {v:.2f}%",
                extra={"fecha": fecha.date().isoformat()})
