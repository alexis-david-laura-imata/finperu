"""verificar_entorno.py detecta librerías faltantes (el panel falló porque faltaba pdfplumber)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verificar_entorno as ve  # noqa: E402


def test_lee_requirements():
    req = ve.requisitos()
    assert "pdfplumber" in req and "pandas" in req and "mcp" in req
    assert all(" " not in r and ">" not in r for r in req)


def test_detecta_faltantes(monkeypatch):
    monkeypatch.setattr(ve, "requisitos", lambda: ["pandas", "libreria-inexistente-finperu"])
    assert ve.faltantes() == ["libreria-inexistente-finperu"]


def test_entorno_actual_completo():
    assert ve.faltantes() == []
