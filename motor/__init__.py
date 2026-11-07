"""FinPerú — motor financiero auditable para empresas peruanas."""
from pathlib import Path as _Path

try:
    __version__ = (_Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip()
except OSError:
    __version__ = "0.0.0"

REPOSITORIO = "alexis-david-laura-imata/finperu"
