"""Pruebas de la API del panel (sin abrir navegador)."""
import time

import pytest
from fastapi.testclient import TestClient

from motor import config
from publicos import ruta
from web.app import app

c = TestClient(app)


def test_estado_y_empresas():
    assert c.get("/api/estado").json()["version"]
    r = c.get("/api/empresas", params={"q": "laive"}).json()
    assert r[0]["rpj"] == "CI0011"
    assert r[0]["industria_sugerida"] == "Food Processing"   # CIIU 1520 (lácteos)


def test_vista_previa_laive():
    v = c.get("/api/vista_previa", params={"rpj": "CI0011", "anio": 2023, "via": "espejo"}).json()
    assert v["deuda_financiera"] == 113678 and v["cuadra"] is True


def test_generar_y_descargar():
    csv = ruta("par-yield-curve-rates-2020-2023.csv")
    if not csv.exists():
        pytest.skip("falta CSV del curso")
    pedido = {"rpj": "CI0011", "anio": 2023, "industria": "Food Processing", "modo": "archivo", "via_smv": "espejo",
              "sobrescribir": {"inflacion_pe": 0.0341, "inflacion_us": 0.034, "riesgo_pais": 0.0162,
                               "prima": 0.06799170755600067, "beta_u": 0.61, "rf": 0.0388},
              "kd_tabla": [{"tipo": "SOBREGIROS", "entidad": "BCP", "tasa_min": 0.0815, "tasa_max": 0.0876, "corriente": 25935},
                           {"tipo": "SOBREGIROS", "entidad": "Scotiabank", "tasa_min": 0.0785, "corriente": 51706},
                           {"tipo": "PRESTAMOS BANCARIOS", "entidad": "BCP", "tasa_min": 0.0355, "tasa_max": 0.0555,
                            "corriente": 11027, "no_corriente": 15805},
                           {"tipo": "PRESTAMOS BANCARIOS", "entidad": "BBVA", "tasa_min": 0.0525, "corriente": 3700,
                            "no_corriente": 5505}]}
    id_ = c.post("/api/generar", json=pedido).json()["id"]
    for _ in range(120):
        t = c.get(f"/api/trabajos/{id_}").json()
        if t["estado"] != "trabajando":
            break
        time.sleep(0.5)
    assert t["estado"] == "listo", t
    assert abs(t["resultado"]["resultados"]["wacc"] - 0.090667) < 1e-6
    carpeta = t["resultado"]["carpeta"].replace("\\", "/").split("/")[-1]
    assert any(h["carpeta"] == carpeta for h in c.get("/api/historial").json())
    x = c.get(f"/api/modelos/{carpeta}/excel")
    assert x.status_code == 200 and x.content[:2] == b"PK"
    assert c.get("/api/modelos/..%2F..%2Fmotor/excel").status_code == 404   # no sale de /salidas


def test_kd_desde_pdf_subido():
    from motor import config as cfg
    pdf = ruta("19379e9c-920a-4147-bde0-ae4d56869b84.pdf")
    if not pdf.exists():
        pytest.skip("falta PDF Laive")
    import os
    os.environ["FINPERU_VIA_SMV"] = "espejo"
    cfg.VIA_SMV = "espejo"
    r = c.post("/api/kd_pdf_subir", data={"rpj": "CI0011", "anio": "2023"},
               files={"archivo": ("laive.pdf", pdf.read_bytes(), "application/pdf")})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["cuadra"] and abs(j["kd_estimado"] - 0.0699744) < 1e-6
    assert j["kd_pdf"]["pagina"] == 38
