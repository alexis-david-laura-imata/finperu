"""Lector de la nota de deuda ("Otros pasivos financieros") de los EEFF auditados en PDF.

Usa pdfplumber (sin Java ni Ghostscript). No asume un formato fijo:
- Ubica la nota por su título (otros pasivos financieros, obligaciones financieras, préstamos...).
- Reconoce en cada fila: entidad, tasa (rango "Entre a y b", "a - b", "a%" o "a"), moneda,
  vencimiento y la cola de importes, sin depender del orden de esas columnas.
- Une filas cuyo nombre se partió en dos líneas (el importe queda "en medio").
- Decide qué bloque de columnas es el año evaluado comparando los totales con la deuda del
  balance de la SMV (1D0309 + 1D0401). Así detecta incluso encabezados con errores de tipeo.

El resultado SIEMPRE se muestra al usuario para confirmar: el lector propone, el usuario decide.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..eventos import emitir

TITULO = re.compile(
    r"^\s*(?:nota\s+)?\d{1,2}\s*[.)-]?\s*(otros\s+pasivos\s+financieros|obligaciones\s+financieras|"
    r"pr[eé]stamos\s+y\s+obligaciones|deuda\s+financiera|pasivos\s+financieros|pr[eé]stamos\s+bancarios|"
    r"obligaciones\s+con\s+entidades|otras\s+obligaciones\s+financieras)\b", re.I)
SIGUIENTE_NOTA = re.compile(r"^\s*\d{1,2}\s*[.)-]?\s+[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ,]{6,}$")
NARRATIVA = re.compile(r"^\s*\([b-z]\)\s+\S+(\s+\S+){8,}")          # "(b) Los fondos provenientes de ..."
RUIDO = re.compile(r"^\s*(notas a los estados|\(continuaci[oó]n\)|-\s*\d+\s*-|_{3,}|página|pag\.)", re.I)
NUM = re.compile(r"^\(?(?:\d{1,3}(?:[.,]\d{3})+|\d+)\)?$|^[-–—]$")
TIPOS = [("SOBREGIRO", "SOBREGIROS"), ("ARRENDAMIENTO", "ARRENDAMIENTO FINANCIERO"), ("LEASING", "ARRENDAMIENTO FINANCIERO"),
         ("PRESTAMO", "PRESTAMOS BANCARIOS"), ("PAGARE", "PAGARES"), ("BONO", "BONOS"), ("PAPEL", "PAPELES COMERCIALES"),
         ("FACTOR", "FACTORING"), ("CARTA", "CARTAS FIANZA"), ("OBLIGACION", "OBLIGACIONES"), ("TITULIZ", "BONOS")]
MONEDA = re.compile(r"(S/\.?\s*y\s*US\$|US\$\s*y\s*S/\.?|US\$|USD|S/\.?|PEN|EUR|Soles|D[oó]lares)", re.I)
TASA_RANGO = re.compile(r"(?:entre\s+)?(\d{1,2}(?:[.,]\d{1,4})?)\s*%?\s*(?:y|a|[-–])\s*(\d{1,2}(?:[.,]\d{1,4})?)\s*%?", re.I)
TASA_UNA = re.compile(r"(?<![\d/])(\d{1,2}[.,]\d{1,4})\s*%?")
ANIO = re.compile(r"\b(19|20)\d{2}\b")


def _sin_tildes(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().upper()


def _num(t: str) -> float:
    t = t.strip()
    if t in "-–—":
        return 0.0
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", t):
        t = t.replace(",", "")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", t):
        t = t.replace(".", "")
    v = float(t)
    return -v if neg else v


def _f(t: str) -> float:
    return float(t.replace(",", "."))


@dataclass
class LineaExtraida:
    tipo: str
    entidad: str
    tasa_min: float | None
    tasa_max: float | None
    moneda: str
    vencimiento: str
    importes: list[float]
    texto: str
    corriente: float = 0
    no_corriente: float = 0
    total: float = 0


@dataclass
class ResultadoNota:
    encontrada: bool
    pagina: int | None = None
    lineas: list[dict] = field(default_factory=list)
    total_extraido: float | None = None
    deuda_esf: float | None = None
    cuadra: bool = False
    bloque_usado: int | None = None
    avisos: list[str] = field(default_factory=list)
    texto_nota: str = ""

    def como_dict(self) -> dict:
        return asdict(self)


def _cola_numerica(tokens: list[str]) -> int:
    n = 0
    for t in reversed(tokens):
        if NUM.match(t):
            n += 1
        else:
            break
    return n


def _lineas_nota(pdf_path: Path) -> tuple[int | None, list[str], list[str]]:
    """Devuelve (página, líneas de la tabla principal, bloque completo de la nota con sub-notas)."""
    import pdfplumber
    with pdfplumber.open(str(pdf_path)) as pdf:
        textos = [(p.extract_text() or "") for p in pdf.pages]
    return _buscar_nota(textos)


def _buscar_nota(textos: list[str]) -> tuple[int | None, list[str], list[str]]:
    for i, t in enumerate(textos):
        ls = t.splitlines()
        for j, l in enumerate(ls):
            if TITULO.match(l):
                bloque = ls[j:] + sum((textos[x].splitlines() for x in range(i + 1, min(i + 3, len(textos)))), [])
                cerca = "\n".join(bloque[:40])
                if re.search(r"tasa|inter[eé]s|corriente", cerca, re.I) and \
                        sum(_cola_numerica(x.split()) >= 3 for x in bloque[:40]) >= 2:
                    tabla, completo = [], []
                    en_tabla = True
                    for k, x in enumerate(bloque[1:], start=1):
                        if k > 3 and SIGUIENTE_NOTA.match(x):
                            break
                        completo.append(x)
                        if k > 3 and NARRATIVA.match(x):
                            en_tabla = False
                        if en_tabla:
                            tabla.append(x)
                    return i + 1, tabla, completo
    return None, [], []


SUBNOTA = re.compile(r"^\s*\(([a-z])\)\s")
TASA_SUELTA = re.compile(r"(?<![\d.,/])(\d{1,2}[.,]\d{1,2})(?![\d.,/])")


def _tasas_subnota(completo: list[str], letra: str) -> tuple[float | None, float | None]:
    """Busca tasas (%) dentro de la sub-nota '(letra)' de la misma nota."""
    dentro, vals = False, []
    for l in completo:
        m = SUBNOTA.match(l)
        if m:
            dentro = m.group(1) == letra
            if not dentro and vals:
                break
        if dentro:
            cand = [float(x.replace(",", ".")) for x in re.findall(r"(\d{1,2}[.,]\d{1,2})\s*%", l)]
            if not cand and re.search(r"\d{1,2}/\d{1,2}/\d{2,4}|semestral|trimestral|anual", l, re.I):
                cand = [float(x.replace(",", ".")) for x in TASA_SUELTA.findall(l)]
            vals += [v for v in cand if 0.3 <= v <= 30]
    if not vals:
        return None, None
    return (min(vals), max(vals)) if max(vals) != min(vals) else (vals[0], None)


def extraer(pdf_path: str | Path, deuda_esf: float | None = None, deuda_esf_anterior: float | None = None,
            anio: int | None = None, tasa_respaldo: float | None = None) -> ResultadoNota:
    pdf_path = Path(pdf_path)
    pag, lineas, completo = _lineas_nota(pdf_path)
    if pag is None:
        emitir("aviso", f"No encontré la nota de deuda en {pdf_path.name}")
        return ResultadoNota(encontrada=False, deuda_esf=deuda_esf,
                             avisos=["No se encontró la nota de 'otros pasivos financieros' en el PDF."])
    emitir("pdf", f"Nota de deuda encontrada en la página {pag} de {pdf_path.name}")
    return extraer_de_lineas(lineas, completo, pag, deuda_esf, deuda_esf_anterior, anio, tasa_respaldo)


def extraer_de_lineas(lineas: list[str], completo: list[str], pag: int, deuda_esf: float | None = None,
                      deuda_esf_anterior: float | None = None, anio: int | None = None,
                      tasa_respaldo: float | None = None) -> ResultadoNota:
    utiles = [l for l in lineas if l.strip() and not RUIDO.match(l)]

    def solo_anios(toks):
        return len(toks) >= 2 and all(re.fullmatch(r"(19|20)\d{2}", t) for t in toks)

    # encabezado con años por columna (p.ej. "2025 2024 2025 2024 2025 2024")
    anios_cols = next(([int(t) for t in l.split()] for l in utiles[:15] if solo_anios(l.split())), None)
    solo_num = [len(l.split()) for l in utiles if l.split() and all(NUM.match(t) for t in l.split())
                and not solo_anios(l.split())]
    k = max(set(solo_num), key=solo_num.count) if solo_num else 6
    k = k if k in (2, 3, 4, 6) else 6

    tipo_actual = "OTROS"
    extraidas: list[LineaExtraida] = []
    pendiente_nombre: str | None = None
    pendientes_importes: list[float] | None = None
    letras: dict[int, str] = {}

    def tipo_de(texto: str) -> str | None:
        s = _sin_tildes(texto)
        for clave, tipo in TIPOS:
            if clave in s:
                return tipo
        return None

    def es_tipo(texto: str) -> str | None:
        if re.match(r"^\s*\([a-z]\)\s", texto) or texto.rstrip().endswith(":") or \
                re.search(r"rubro|comprende|siguiente|detall|presenta|composici", texto, re.I):
            return None
        texto = re.sub(r"\([a-z]\)", " ", texto).strip().rstrip("-–—:").strip()
        if not texto or _cola_numerica(texto.split()) or TASA_UNA.search(texto) or MONEDA.search(texto):
            return None
        if len(texto.split()) > 7:
            return None
        return tipo_de(texto)

    def parsear_medio(medio: str) -> tuple[str, float | None, float | None, str, str]:
        medio = re.sub(r"\([a-z]\)", " ", medio)                       # llamadas (c)
        mon = MONEDA.search(medio)
        moneda = mon.group(1).replace(" ", "") if mon else ""
        sin_mon = MONEDA.sub(" ", medio)
        venc = ""
        a = ANIO.search(sin_mon)
        if a:
            venc = a.group(0)
            sin_mon = sin_mon[:a.start()] + " " + sin_mon[a.end():]
        rr = TASA_RANGO.search(sin_mon)
        tmin = tmax = None
        corte = None
        if rr and (rr.group(0).lower().startswith("entre") or "%" in rr.group(0) or
                   ("." in rr.group(1) or "," in rr.group(1))):
            tmin, tmax = _f(rr.group(1)), _f(rr.group(2))
            corte = rr.start()
        else:
            u = TASA_UNA.search(sin_mon)
            if u:
                tmin = _f(u.group(1))
                corte = u.start()
        ent = sin_mon[:corte] if corte is not None else sin_mon
        ent = re.sub(r"\bentre\b\s*$", "", ent, flags=re.I)
        ent = re.sub(r"\s+[-–]\s*$", "", ent).strip(" -–")
        return " ".join(ent.split()), tmin, tmax, moneda, venc

    def agregar(medio: str, importes: list[float], texto: str):
        letra = re.search(r"\(([a-z])\)", medio)
        ent, tmin, tmax, mon, venc = parsear_medio(medio)
        tipo = tipo_actual if tipo_actual != "OTROS" else (tipo_de(ent) or "OTROS")
        extraidas.append(LineaExtraida(tipo, ent, tmin, tmax, mon, venc, importes, texto))
        if letra:
            letras[len(extraidas) - 1] = letra.group(1)

    for l in utiles:
        toks = l.split()
        if solo_anios(toks):
            continue
        n = _cola_numerica(toks)
        t = es_tipo(l)
        if t:
            tipo_actual, pendiente_nombre = t, None
            continue
        if n == len(toks) and n >= 2:                                   # línea solo con números
            if pendiente_nombre:
                pendientes_importes = [_num(x) for x in toks[-k:]]
            continue
        if n >= k:                                                      # fila completa
            medio = " ".join(toks[:-k])
            if pendiente_nombre and not re.search(r"[a-z]{3,}", medio.split(" ")[0] if medio else ""):
                medio = pendiente_nombre + " " + medio
            agregar(medio, [_num(x) for x in toks[-k:]], l.strip())
            pendiente_nombre = None
            continue
        if pendientes_importes is not None and pendiente_nombre:          # cierre de fila partida
            agregar(pendiente_nombre + " " + l, pendientes_importes, f"{pendiente_nombre} | {l.strip()}")
            pendiente_nombre, pendientes_importes = None, None
            continue
        if not re.search(r"\d", l) and len(l.split()) <= 10 and \
                not re.search(r"tasa|corriente|vencimiento|saldo|moneda|acreedor|total", l, re.I):
            pendiente_nombre = l.strip()
        else:
            pendiente_nombre = None

    res = ResultadoNota(encontrada=True, pagina=pag, deuda_esf=deuda_esf, texto_nota="\n".join(utiles[:120]))
    if not extraidas:
        res.avisos.append("Encontré la nota pero no pude leer filas con tasa e importes.")
        return res

    # ¿qué columnas son corriente / no corriente del año evaluado?
    def mapa_intercalado(pos_anio: int) -> tuple[int, int, int | None]:
        # columnas: [corr a, corr b, nocorr a, nocorr b, total a, total b]
        return pos_anio, 2 + pos_anio, (4 + pos_anio if k == 6 else None)

    mapas: list[tuple[int, int, int | None]] = []
    intercalado = bool(anios_cols and len(anios_cols) == k and k in (4, 6) and anios_cols[0] != anios_cols[1] and
                       anios_cols[0] == anios_cols[2])
    if intercalado:
        mapas = [mapa_intercalado(0), mapa_intercalado(1)]
    elif k == 6:
        mapas = [(0, 1, 2), (3, 4, 5)]
    elif k == 4:
        mapas = [(0, 1, None), (2, 3, None)]
    elif k == 3:
        mapas = [(0, 1, 2)]
    else:
        mapas = [(0, 1, None)]

    def total_mapa(m):
        return sum(x.importes[m[0]] + x.importes[m[1]] for x in extraidas)

    totales = [total_mapa(m) for m in mapas]
    b_usado = 0
    if deuda_esf is not None:
        b_usado = min(range(len(mapas)), key=lambda b: abs(totales[b] - deuda_esf))
    elif anios_cols and anio in anios_cols and intercalado:
        b_usado = anios_cols.index(anio)
    elif deuda_esf_anterior is not None and len(mapas) == 2 and \
            abs(totales[0] - deuda_esf_anterior) < abs(totales[1] - deuda_esf_anterior):
        b_usado = 1
    if b_usado:
        res.avisos.append("El año evaluado no está en las primeras columnas de la nota; se tomaron las que cuadran.")
    res.bloque_usado = b_usado
    ci, ni, _ = mapas[b_usado]

    filas = []
    for idx, x in enumerate(extraidas):
        x.corriente, x.no_corriente = x.importes[ci], x.importes[ni]
        if x.corriente + x.no_corriente == 0:
            continue                                   # sin saldo en el año evaluado
        origen = "tabla de la nota"
        if x.tasa_min is None and idx in letras:
            tmin, tmax = _tasas_subnota(completo, letras[idx])
            if tmin is not None:
                x.tasa_min, x.tasa_max, origen = tmin, tmax, f"sub-nota ({letras[idx]})"
        nota = f"PDF pág. {pag}, {origen}: {x.texto[:110]}"
        if x.tasa_min is None:
            if tasa_respaldo is not None:
                x.tasa_min = tasa_respaldo * 100
                nota = (f"TASA NO REVELADA en la nota (pág. {pag}); se usa el Kd aproximado "
                        f"{tasa_respaldo:.2%} como respaldo. Revisar. Fila: {x.texto[:80]}")
                res.avisos.append(f"'{x.entidad}': la nota no revela la tasa; se puso el Kd aproximado "
                                  f"({tasa_respaldo:.2%}). Revísala.")
            else:
                res.avisos.append(f"'{x.entidad}': la nota no revela la tasa. Complétala a mano.")
        filas.append({"tipo": x.tipo, "entidad": x.entidad,
                      "tasa_min": None if x.tasa_min is None else round(x.tasa_min / 100, 6),
                      "tasa_max": None if x.tasa_max is None else round(x.tasa_max / 100, 6),
                      "moneda": x.moneda or "S/", "vencimiento": x.vencimiento,
                      "corriente": x.corriente, "no_corriente": x.no_corriente, "nota": nota})
    res.lineas = filas
    res.total_extraido = sum(f["corriente"] + f["no_corriente"] for f in filas)
    if deuda_esf is not None:
        res.cuadra = abs(res.total_extraido - deuda_esf) <= 1
        if not res.cuadra:
            res.avisos.append(f"La tabla leída suma {res.total_extraido:,.0f} y la deuda del balance es "
                              f"{deuda_esf:,.0f}. Revisa filas faltantes o importes.")
    emitir("pdf", f"Nota de deuda: {len(filas)} líneas, total {res.total_extraido:,.0f}"
                  + (f" vs ESF {deuda_esf:,.0f} → {'cuadra' if res.cuadra else 'NO cuadra'}" if deuda_esf else ""))
    return res
