"""El actualizador reemplaza el código y nunca toca los datos del usuario."""
import zipfile

from motor import actualizador


def _instalacion_falsa(raiz):
    (raiz / "motor").mkdir(parents=True)
    (raiz / "motor" / "viejo.py").write_text("# viejo")
    (raiz / "instalador" / "bin").mkdir(parents=True)
    (raiz / "instalador" / "bin" / "uv.exe").write_text("binario")
    (raiz / "instalador" / "instalar.ps1").write_text("viejo")
    (raiz / "salidas" / "Laive_2023").mkdir(parents=True)
    (raiz / "salidas" / "Laive_2023" / "modelo.xlsx").write_text("mi modelo")
    (raiz / "datos_cache").mkdir()
    (raiz / "config.local.json").write_text('{"mio": 1}')
    (raiz / "VERSION").write_text("0.2.0")


def _zip_nuevo(ruta):
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("finperu-main/VERSION", "9.9.9")
        z.writestr("finperu-main/motor/nuevo.py", "# nuevo")
        z.writestr("finperu-main/instalador/instalar.ps1", "nuevo")
        z.writestr("finperu-main/salidas/Laive_2023/modelo.xlsx", "PISADO")       # debe ignorarse
        z.writestr("finperu-main/config.local.json", "PISADO")                    # debe ignorarse
        z.writestr("finperu-main/plantillas/_fuente_curso/x.xlsx", "PISADO")      # debe ignorarse
    return ruta


def test_aplicar_conserva_datos(tmp_path, monkeypatch):
    raiz = tmp_path / "FinPeru"
    _instalacion_falsa(raiz)
    monkeypatch.setattr(actualizador, "RAIZ", raiz)
    res = actualizador.aplicar(str(_zip_nuevo(tmp_path / "nuevo.zip")), sincronizar_dependencias=False)

    assert res["ok"] and res["version"] == "9.9.9"
    assert (raiz / "motor" / "nuevo.py").exists()
    assert not (raiz / "motor" / "viejo.py").exists()                     # código reemplazado
    assert (raiz / "instalador" / "instalar.ps1").read_text() == "nuevo"
    assert (raiz / "instalador" / "bin" / "uv.exe").exists()              # uv se conserva
    assert (raiz / "salidas" / "Laive_2023" / "modelo.xlsx").read_text() == "mi modelo"
    assert (raiz / "config.local.json").read_text() == '{"mio": 1}'
    assert not (raiz / "plantillas" / "_fuente_curso").exists()
    respaldos = list((raiz / "datos_cache" / "respaldos").iterdir())
    assert respaldos and (respaldos[0] / "motor" / "viejo.py").exists()


def test_comparar_versiones():
    assert actualizador._tupla("v0.10.0") > actualizador._tupla("0.9.3")
    assert actualizador._tupla("0.2.0") == actualizador._tupla("v0.2.0")
