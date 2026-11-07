"""Lienzo: una sola interfaz para escribir el modelo en Excel de dos maneras.

- LienzoArchivo (openpyxl): rápido, sin abrir Excel. Sirve para pruebas y para generar en segundo plano.
- LienzoVivo (xlwings, solo Windows): abre Excel visible y escribe celda por celda, con pausa,
  resaltando cada celda y mostrando el paso en la barra de estado. Es el "show".

Las dos reciben exactamente las mismas instrucciones, así el resultado es idéntico (estandarizado).

Estilos (convención de modelado financiero):
  dato      -> azul sobre celeste: dato de entrada que viene de una fuente (auditable)
  formula   -> negro: cálculo dentro de la misma hoja
  vinculo   -> verde: trae un valor de otra hoja
  usuario   -> azul sobre naranja claro: dato ingresado/confirmado por el usuario (supuesto)
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from ..eventos import emitir

# ---------------------------------------------------------------- paleta
AZUL_OSCURO = (31, 56, 100)
BLANCO = (255, 255, 255)
AZUL_DATO = (0, 0, 192)
CELESTE = (234, 241, 251)
NARANJA_CLARO = (252, 228, 214)
VERDE_VINCULO = (0, 112, 60)
GRIS_TEXTO = (89, 89, 89)
GRIS_FONDO = (242, 242, 242)
AMARILLO_VIVO = (255, 217, 0)
VERDE_OK = (198, 239, 206)
ROJO_MAL = (255, 199, 206)

ESTILOS: dict[str, dict[str, Any]] = {
    "titulo":    {"bold": True, "size": 16, "color": AZUL_OSCURO},
    "subtitulo": {"bold": True, "size": 12, "color": AZUL_OSCURO},
    "cabecera":  {"bold": True, "color": BLANCO, "fill": AZUL_OSCURO},
    "etiqueta":  {},
    "etiqueta_b": {"bold": True},
    "dato":      {"color": AZUL_DATO, "fill": CELESTE},
    "usuario":   {"color": AZUL_DATO, "fill": NARANJA_CLARO},
    "formula":   {"color": (0, 0, 0)},
    "formula_b": {"color": (0, 0, 0), "bold": True, "fill": GRIS_FONDO},
    "vinculo":   {"color": VERDE_VINCULO},
    "resultado": {"bold": True, "size": 12, "color": AZUL_OSCURO, "fill": (221, 235, 247)},
    "nota":      {"italic": True, "color": GRIS_TEXTO, "size": 9},
    "enlace":    {"color": (5, 99, 193), "underline": True, "size": 9},
    "texto":     {},
}

FORMATOS = {"pct": "0.00%", "pct4": "0.0000%", "num": "#,##0", "num2": "#,##0.00",
            "dec4": "0.0000", "fecha": "dd/mm/yyyy", "texto": "@"}


def _hex(rgb):
    return "%02X%02X%02X" % rgb


def _es_formula(v) -> bool:
    return isinstance(v, str) and v.startswith("=")


def _es_vinculo(f: str) -> bool:
    return "!" in f


class Lienzo:
    """Interfaz común."""
    vivo = False

    def __init__(self, velocidad: float = 1.0):
        self.velocidad = velocidad          # 0 = sin pausas; 1 = demo normal; 2 = más lento
        self.nombres: dict[str, str] = {}   # nombre definido -> referencia
        self.hoja_actual: str | None = None

    # -- a implementar
    def nueva_hoja(self, nombre: str, color_pestana=None): ...
    def _escribir(self, hoja, celda, valor, estilo, formato): ...
    def _comentario(self, hoja, celda, texto): ...
    def _enlace(self, hoja, celda, url, texto): ...
    def _nombre(self, nombre, ref): ...
    def ancho(self, hoja, col: str, ancho: float): ...
    def _estado(self, msg: str): ...
    def formato_condicional_ok(self, hoja, rango: str): ...
    def guardar(self, ruta: Path): ...
    def cerrar(self): ...

    # -- comunes
    def paso(self, msg: str, pausa: float = 0.8):
        emitir("excel_paso", msg)
        self._estado(msg)
        self._pausa(pausa)

    def _pausa(self, s: float):
        if self.vivo and self.velocidad > 0 and s > 0:
            time.sleep(s * self.velocidad)

    def escribir(self, hoja: str, celda: str, valor: Any, estilo: str | None = None, formato: str | None = None,
                 nombre: str | None = None, comentario: str | None = None, pausa: float = 0.12):
        if estilo is None:
            estilo = ("vinculo" if _es_vinculo(valor) else "formula") if _es_formula(valor) else "texto"
        self._escribir(hoja, celda, valor, estilo, FORMATOS.get(formato, formato))
        if nombre:
            ref = f"='{hoja}'!${re.match(r'[A-Z]+', celda).group()}${re.search(r'\d+', celda).group()}"
            self._nombre(nombre, ref)
            self.nombres[nombre] = ref
        if comentario:
            self._comentario(hoja, celda, comentario)
        self._pausa(pausa)

    def enlace(self, hoja, celda, url, texto):
        self._enlace(hoja, celda, url, texto)

    def fila(self, hoja: str, celda: str, valores: list, pausa: float = 0.05):
        """Escribe una fila de valores de una sola vez (tablas largas)."""
        self._fila(hoja, celda, valores)
        self._pausa(pausa)

    def estilo_rango(self, hoja: str, rango: str, estilo: str, formato: str | None = None): ...
    def _fila(self, hoja, celda, valores): ...


# ================================================================= openpyxl
class LienzoArchivo(Lienzo):
    vivo = False

    def __init__(self, velocidad: float = 0):
        super().__init__(0)
        from openpyxl import Workbook
        self.wb = Workbook()
        self._primera = True

    def nueva_hoja(self, nombre, color_pestana=None):
        if self._primera:
            ws = self.wb.active
            ws.title = nombre
            self._primera = False
        else:
            ws = self.wb.create_sheet(nombre)
        ws.sheet_view.showGridLines = False
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        if color_pestana:
            ws.sheet_properties.tabColor = _hex(color_pestana)
        self.hoja_actual = nombre
        return ws

    def _escribir(self, hoja, celda, valor, estilo, formato):
        from openpyxl.styles import Font, PatternFill
        c = self.wb[hoja][celda]
        c.value = valor
        e = ESTILOS.get(estilo, {})
        c.font = Font(bold=e.get("bold", False), italic=e.get("italic", False), size=e.get("size", 11),
                      color=_hex(e["color"]) if "color" in e else None,
                      underline="single" if e.get("underline") else None, name="Calibri")
        if "fill" in e:
            c.fill = PatternFill("solid", fgColor=_hex(e["fill"]))
        if formato:
            c.number_format = formato

    def _fila(self, hoja, celda, valores):
        from openpyxl.utils.cell import coordinate_from_string, column_index_from_string
        col, row = coordinate_from_string(celda)
        c0 = column_index_from_string(col)
        ws = self.wb[hoja]
        for k, v in enumerate(valores):
            ws.cell(row=row, column=c0 + k, value=v)

    def estilo_rango(self, hoja, rango, estilo, formato=None):
        from openpyxl.styles import Font, PatternFill
        e = ESTILOS.get(estilo, {})
        font = Font(bold=e.get("bold", False), italic=e.get("italic", False), size=e.get("size", 11),
                    color=_hex(e["color"]) if "color" in e else None, name="Calibri")
        fill = PatternFill("solid", fgColor=_hex(e["fill"])) if "fill" in e else None
        fmt = FORMATOS.get(formato, formato)
        sel = self.wb[hoja][rango if ":" in rango else f"{rango}:{rango}"]
        for fila_c in sel:
            for c in fila_c:
                c.font = font
                if fill:
                    c.fill = fill
                if fmt:
                    c.number_format = fmt

    def _comentario(self, hoja, celda, texto):
        from openpyxl.comments import Comment
        cm = Comment(texto, "FinPeru MCP")
        cm.width, cm.height = 420, 160
        self.wb[hoja][celda].comment = cm

    def _enlace(self, hoja, celda, url, texto):
        c = self.wb[hoja][celda]
        c.value = texto
        c.hyperlink = url
        self._escribir(hoja, celda, texto, "enlace", None)

    def _nombre(self, nombre, ref):
        from openpyxl.workbook.defined_name import DefinedName
        self.wb.defined_names[nombre] = DefinedName(nombre, attr_text=ref.lstrip("="))

    def ancho(self, hoja, col, ancho):
        self.wb[hoja].column_dimensions[col].width = ancho

    def _estado(self, msg):
        pass

    def formato_condicional_ok(self, hoja, rango):
        from openpyxl.formatting.rule import CellIsRule
        from openpyxl.styles import PatternFill
        ws = self.wb[hoja]
        ws.conditional_formatting.add(rango, CellIsRule(operator="equal", formula=['"OK"'],
                                                        fill=PatternFill("solid", fgColor=_hex(VERDE_OK))))
        ws.conditional_formatting.add(rango, CellIsRule(operator="equal", formula=['"REVISAR"'],
                                                        fill=PatternFill("solid", fgColor=_hex(ROJO_MAL))))

    def activar(self, hoja):
        self.wb.active = self.wb.sheetnames.index(hoja)

    def guardar(self, ruta):
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        self.wb.save(ruta)
        return ruta

    def cerrar(self):
        pass


# ================================================================= xlwings (vivo)
class LienzoVivo(Lienzo):
    vivo = True

    def __init__(self, velocidad: float = 1.0):
        super().__init__(velocidad)
        try:  # necesario cuando se llama desde un hilo (panel web / servidor MCP)
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:  # noqa: BLE001
            pass
        import xlwings as xw
        self.xw = xw
        self.app = xw.App(visible=True, add_book=False)
        self.app.screen_updating = True
        try:
            self.app.api.WindowState = -4137  # xlMaximized
        except Exception:  # noqa: BLE001
            pass
        self.wb = self.app.books.add()
        self._primera = True
        emitir("excel", "Excel abierto en modo en vivo")

    def _hoja(self, nombre):
        ws = self.wb.sheets[nombre]
        if self.hoja_actual != nombre:
            ws.activate()
            self.hoja_actual = nombre
        return ws

    def nueva_hoja(self, nombre, color_pestana=None):
        if self._primera:
            ws = self.wb.sheets[0]
            ws.name = nombre
            self._primera = False
        else:
            ws = self.wb.sheets.add(nombre, after=self.wb.sheets[-1])
        ws.activate()
        self.hoja_actual = nombre
        try:
            self.app.api.ActiveWindow.DisplayGridlines = False
            if color_pestana:
                r, g, b = color_pestana
                ws.api.Tab.Color = r + g * 256 + b * 65536
        except Exception:  # noqa: BLE001
            pass
        try:  # impresión: horizontal, 1 página de ancho (PrintCommunication off = rápido)
            self.app.api.PrintCommunication = False
            ps = ws.api.PageSetup
            ps.Orientation, ps.Zoom, ps.FitToPagesWide, ps.FitToPagesTall = 2, False, 1, False
            self.app.api.PrintCommunication = True
        except Exception:  # noqa: BLE001
            try:
                self.app.api.PrintCommunication = True
            except Exception:  # noqa: BLE001
                pass
        self._pausa(0.5)
        return ws

    def _escribir(self, hoja, celda, valor, estilo, formato):
        ws = self._hoja(hoja)
        rng = ws.range(celda)
        e = ESTILOS.get(estilo, {})
        if self.velocidad > 0:
            try:
                rng.select()
                rng.color = AMARILLO_VIVO
            except Exception:  # noqa: BLE001
                pass
        if formato:
            rng.number_format = formato
        if _es_formula(valor):
            rng.formula = valor
        else:
            rng.value = valor
        f = rng.font
        f.bold = e.get("bold", False)
        f.italic = e.get("italic", False)
        f.size = e.get("size", 11)
        if "color" in e:
            f.color = e["color"]
        if e.get("underline"):
            try:
                rng.api.Font.Underline = 2
            except Exception:  # noqa: BLE001
                pass
        if self.velocidad > 0:
            self._pausa(0.08)
        rng.color = e.get("fill")  # None limpia el resaltado

    def _fila(self, hoja, celda, valores):
        ws = self._hoja(hoja)
        rng = ws.range(celda).resize(1, len(valores))
        if self.velocidad > 0:
            try:
                rng.color = AMARILLO_VIVO
                if rng.row % 8 == 0:
                    rng.select()
            except Exception:  # noqa: BLE001
                pass
        rng.value = [None if (isinstance(v, float) and v != v) else v for v in valores]
        if self.velocidad > 0:
            self._pausa(0.04)
            rng.color = None

    def estilo_rango(self, hoja, rango, estilo, formato=None):
        rng = self._hoja(hoja).range(rango)
        e = ESTILOS.get(estilo, {})
        f = rng.font
        f.bold = e.get("bold", False)
        f.italic = e.get("italic", False)
        f.size = e.get("size", 11)
        if "color" in e:
            f.color = e["color"]
        rng.color = e.get("fill")
        fmt = FORMATOS.get(formato, formato)
        if fmt:
            rng.number_format = fmt

    def _comentario(self, hoja, celda, texto):
        rng = self._hoja(hoja).range(celda)
        try:
            rng.api.ClearComments()
            cm = rng.api.AddComment(texto)
            cm.Shape.Width, cm.Shape.Height = 320, 120
        except Exception:  # noqa: BLE001
            pass

    def _enlace(self, hoja, celda, url, texto):
        rng = self._hoja(hoja).range(celda)
        try:
            rng.add_hyperlink(url, texto)
        except Exception:  # noqa: BLE001
            rng.value = texto
        rng.font.size = 9

    def _nombre(self, nombre, ref):
        try:
            self.wb.names.add(nombre, ref)
        except Exception as e:  # noqa: BLE001
            emitir("aviso", f"No se pudo crear el nombre {nombre}: {e}")

    def ancho(self, hoja, col, ancho):
        self._hoja(hoja).range(f"{col}:{col}").column_width = ancho

    def _estado(self, msg):
        try:
            self.app.api.StatusBar = f"FinPerú MCP — {msg}"
        except Exception:  # noqa: BLE001
            pass

    def formato_condicional_ok(self, hoja, rango):
        rng = self._hoja(hoja).range(rango)
        try:
            fc = rng.api.FormatConditions
            ok = fc.Add(1, 3, '="OK"')          # xlCellValue, xlEqual
            ok.Interior.Color = VERDE_OK[0] + VERDE_OK[1] * 256 + VERDE_OK[2] * 65536
            mal = fc.Add(1, 3, '="REVISAR"')
            mal.Interior.Color = ROJO_MAL[0] + ROJO_MAL[1] * 256 + ROJO_MAL[2] * 65536
        except Exception:  # noqa: BLE001
            pass

    def activar(self, hoja):
        ws = self.wb.sheets[hoja]
        ws.activate()
        self.hoja_actual = hoja
        try:
            ws.range("A1").select()
        except Exception:  # noqa: BLE001
            pass

    def valor(self, hoja, celda):
        return self.wb.sheets[hoja].range(celda).value

    def guardar(self, ruta):
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        self.app.calculate()
        self.wb.save(str(ruta))
        self._estado("Modelo guardado")
        try:
            self.app.api.StatusBar = False
        except Exception:  # noqa: BLE001
            pass
        return ruta

    def cerrar(self):
        pass  # se deja Excel abierto para que el usuario revise
