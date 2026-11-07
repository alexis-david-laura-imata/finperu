"""Sesión de navegador (Playwright/Chromium) con ayudas visuales para el "show".

- Cartel superior con el paso actual (no altera la página: es una capa encima).
- Resaltado amarillo del elemento que se va a usar.
- Velocidad ajustable (slow_mo + pausas) y modo oculto (headless) para trabajar rápido.
"""
from __future__ import annotations

from pathlib import Path

from ..datos.red import Fuente, registrar_archivo
from ..eventos import emitir

_CARTEL_JS = """(t) => {
  let c = document.getElementById('__finperu_cartel');
  if (!c) {
    c = document.createElement('div'); c.id = '__finperu_cartel';
    c.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;background:#1f3864;color:#fff;' +
      'font:600 16px Segoe UI,system-ui,sans-serif;padding:10px 16px;box-shadow:0 2px 8px rgba(0,0,0,.35)';
    document.documentElement.appendChild(c);
  }
  c.textContent = 'FinPerú · ' + t;
}"""


class Navegador:
    def __init__(self, visible: bool = True, velocidad: float = 1.0):
        self.visible = visible
        self.velocidad = max(0.0, velocidad)
        self._pw = self._nav = self.page = None

    def __enter__(self) -> "Navegador":
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        slow = int(250 * self.velocidad) if self.visible else 0
        self._nav = self._pw.chromium.launch(headless=not self.visible, slow_mo=slow,
                                             args=["--start-maximized"] if self.visible else [])
        ctx = self._nav.new_context(viewport=None if self.visible else {"width": 1366, "height": 900},
                                    accept_downloads=True, locale="es-PE")
        self.page = ctx.new_page()
        emitir("navegador", f"Navegador {'visible' if self.visible else 'oculto'} iniciado")
        return self

    def __exit__(self, *exc):
        try:
            if self._nav:
                self._nav.close()
        finally:
            if self._pw:
                self._pw.stop()

    # ------------------------------------------------------------ ayudas
    def pausa(self, s: float = 1.0):
        if self.visible and self.velocidad > 0:
            self.page.wait_for_timeout(int(s * 1000 * self.velocidad))

    def cartel(self, texto: str):
        emitir("navegador", texto)
        if self.visible:
            try:
                self.page.evaluate(_CARTEL_JS, texto)
            except Exception:  # noqa: BLE001
                pass

    def ir(self, url: str, texto: str, espera: str = "domcontentloaded"):
        self.page.goto(url, wait_until=espera, timeout=90000)
        self.cartel(texto)
        self.pausa(0.8)

    def resaltar(self, locator, texto: str | None = None, s: float = 1.2) -> bool:
        try:
            el = locator.first
            if not el.count():
                return False
            el.scroll_into_view_if_needed(timeout=5000)
            el.evaluate("e => { e.style.outline = '4px solid #ffbf47'; e.style.outlineOffset = '2px';"
                        " e.style.background = 'rgba(255,191,71,.25)'; }")
            if texto:
                self.cartel(texto)
            self.pausa(s)
            return True
        except Exception:  # noqa: BLE001
            return False

    def descargar_clic(self, locator, destino: Path, url: str, origen: str, nota: str = "") -> Fuente:
        """Hace clic en un enlace de descarga y guarda el archivo en `destino` (con registro auditable)."""
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with self.page.expect_download(timeout=120000) as d:
            locator.first.click()
        d.value.save_as(str(destino))
        self.pausa(0.6)
        return registrar_archivo(destino, url, origen, nota)
