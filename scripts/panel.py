"""Inicia el panel web local y lo abre en el navegador.

    python scripts\\panel.py            (o doble clic en "Iniciar FinPeru.bat")
"""
import sys
import threading
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import uvicorn  # noqa: E402

PUERTO = 8765
URL = f"http://127.0.0.1:{PUERTO}"

if __name__ == "__main__":
    print(f"FinPerú — panel en {URL}  (cierra esta ventana para detenerlo)")
    threading.Timer(1.5, lambda: webbrowser.open(URL)).start()
    uvicorn.run("web.app:app", host="127.0.0.1", port=PUERTO, log_level="warning")
