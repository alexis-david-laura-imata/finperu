"""Descargas con caché y registro auditable.

Cada archivo descargado queda:
- guardado tal cual llegó en datos_cache/<origen>/...
- con su hash SHA-256
- anotado en datos_cache/registro_fuentes.jsonl (URL, fecha, hash, ruta)

Así cualquier número del Excel se puede rastrear hasta el archivo original.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import requests

from .. import config
from ..eventos import emitir


@dataclass
class Fuente:
    """Procedencia de un archivo o dato."""
    url: str
    archivo: str            # ruta local del archivo crudo
    sha256: str
    descargado: str         # fecha ISO de la descarga (o de la primera vez que se cacheó)
    origen: str             # smv | damodaran | bcrp | tesoro | local | usuario
    nota: str = ""

    def corta(self) -> str:
        return f"{self.origen}: {self.url} ({self.descargado[:10]}, sha256 {self.sha256[:12]})"


@dataclass
class Dato:
    """Un valor con su procedencia. Es la unidad que viaja hasta la celda de Excel."""
    valor: Any
    fuente: Fuente
    detalle: str = ""                       # p.ej. "Food Processing, columna 'Unlevered beta'"
    extra: dict = field(default_factory=dict)

    def comentario(self) -> str:
        """Texto para el comentario de la celda en Excel."""
        partes = [self.detalle, f"Fuente: {self.fuente.url}",
                  f"Descargado: {self.fuente.descargado[:16].replace('T', ' ')}",
                  f"SHA-256: {self.fuente.sha256[:16]}…"]
        if self.fuente.nota:
            partes.append(self.fuente.nota)
        return "\n".join(p for p in partes if p)


def sha256_de(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _registrar(fuente: Fuente) -> None:
    config.REGISTRO_FUENTES.parent.mkdir(parents=True, exist_ok=True)
    with open(config.REGISTRO_FUENTES, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(fuente), ensure_ascii=False) + "\n")


def fuente_local(ruta: Path, origen: str = "local", url: str | None = None, nota: str = "") -> Fuente:
    ruta = Path(ruta)
    fecha = datetime.fromtimestamp(ruta.stat().st_mtime).isoformat(timespec="seconds")
    return Fuente(url=url or ruta.as_uri(), archivo=str(ruta), sha256=sha256_de(ruta),
                  descargado=fecha, origen=origen, nota=nota)


def descargar(url: str, destino: Path, origen: str, *, max_edad_horas: float | None = None,
              metodo: str = "GET", datos: bytes | None = None, cabeceras: dict | None = None,
              validar: Callable[[bytes], None] | None = None, intentos: int = 4,
              timeout: tuple[float, float] = (15, 180), nota: str = "") -> Fuente:
    """Descarga `url` a `destino` (si no está en caché o está vencido) y devuelve su Fuente.

    `validar(contenido)` debe lanzar una excepción si la respuesta no sirve: así nunca se
    cachea basura (p.ej. una página de error con código 200).
    """
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    meta = destino.with_suffix(destino.suffix + ".meta.json")

    if destino.exists() and meta.exists():
        edad_h = (time.time() - destino.stat().st_mtime) / 3600
        if max_edad_horas is None or edad_h <= max_edad_horas:
            info = json.loads(meta.read_text(encoding="utf-8"))
            emitir("cache", f"Usando caché: {destino.name}", url=url)
            return Fuente(**info)

    emitir("descarga", f"Descargando {url}", origen=origen)
    cab = {"User-Agent": config.USER_AGENT}
    cab.update(cabeceras or {})
    ultimo: Exception | None = None
    for intento in range(1, intentos + 1):
        try:
            r = requests.request(metodo, url, data=datos, headers=cab, timeout=timeout)
            if r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            contenido = r.content
            if validar:
                validar(contenido)
            destino.write_bytes(contenido)
            fuente = Fuente(url=url, archivo=str(destino), sha256=hashlib.sha256(contenido).hexdigest(),
                            descargado=datetime.now().isoformat(timespec="seconds"), origen=origen, nota=nota)
            meta.write_text(json.dumps(asdict(fuente), ensure_ascii=False, indent=1), encoding="utf-8")
            _registrar(fuente)
            emitir("descarga_ok", f"Descargado {destino.name} ({len(contenido)/1024:.0f} KB)",
                   url=url, sha256=fuente.sha256[:12])
            return fuente
        except (requests.RequestException, ValueError) as e:
            ultimo = e
            if isinstance(e, requests.HTTPError) and e.response is not None and 400 <= e.response.status_code < 500:
                break  # error nuestro (404, etc.): no tiene sentido reintentar
            espera = min(4 * 2 ** (intento - 1), 60)
            emitir("reintento", f"Fallo {intento}/{intentos} ({e}); reintento en {espera}s", url=url)
            time.sleep(espera)
    raise ConnectionError(f"No se pudo descargar {url}: {ultimo}")


def registrar_archivo(destino: Path, url: str, origen: str, nota: str = "") -> Fuente:
    """Registra un archivo descargado por otro medio (p.ej. el navegador) con el mismo formato
    de caché que `descargar`, para que el resto del motor lo reutilice y quede auditado."""
    destino = Path(destino)
    fuente = Fuente(url=url, archivo=str(destino), sha256=sha256_de(destino),
                    descargado=datetime.now().isoformat(timespec="seconds"), origen=origen, nota=nota)
    destino.with_suffix(destino.suffix + ".meta.json").write_text(
        json.dumps(asdict(fuente), ensure_ascii=False, indent=1), encoding="utf-8")
    _registrar(fuente)
    emitir("descarga_ok", f"Descargado {destino.name} ({destino.stat().st_size/1024:.0f} KB) desde el navegador",
           url=url, sha256=fuente.sha256[:12])
    return fuente
