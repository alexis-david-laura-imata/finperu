# Arquitectura de FinPerú

```
           ┌────────────── interfaces ──────────────┐
           │  web/ (panel)   mcp_server/   scripts/  │
           └──────────────────┬─────────────────────┘
                              │ llaman a
                     motor/generar.py  ── orquesta un modelo
            ┌─────────────────┼──────────────────────────┐
   motor/datos/        motor/metodologia.py       motor/excel/
   (fuentes)           (cálculo + controles)      (lienzo + plantillas)
            └──────── motor/eventos.py (bus de eventos en vivo) ────────┘
                     motor/navegador/ (recorrido visible con Playwright)
```

## Principios
1. **Las interfaces no calculan.** Panel, MCP y CLI solo llaman a `motor.generar`. Una sola verdad.
2. **Todo dato es un `Dato`** (`motor/datos/red.py`): valor + `Fuente` (URL, archivo local, SHA-256, fecha) + detalle.
   Así cada celda del Excel puede llevar su nota de origen.
3. **Todo paso emite un evento** (`motor/eventos.emitir`). El panel lo muestra por SSE; el MCP lo resume;
   también queda en `datos_cache/eventos.jsonl`.
4. **El Excel lleva fórmulas, no números pegados.** Python calcula para verificar; el Excel recalcula por sí solo
   y la hoja *Controles* compara ambos.
5. **El código y los datos del usuario están separados**, para que el actualizador pueda reemplazar el código sin miedo.

## Módulos
| Ruta | Responsabilidad |
|---|---|
| `motor/config.py` | Rutas, parámetros por defecto, User-Agent |
| `motor/datos/red.py` | Descargas con caché, reintentos, hash y registro de fuentes |
| `motor/datos/smv.py` | EEFF de la SMV (SOAP en vivo o espejo smv-eeff), conceptos del plan contable |
| `motor/datos/smv_pdf.py` | Portal SMV: busca y descarga el PDF auditado y el XBRL |
| `motor/datos/nota_deuda.py` | Lee la nota de otros pasivos financieros del PDF y arma la tabla Kd |
| `motor/datos/damodaran.py` | Betas por industria (archivo del año evaluado), prima de mercado (histret) |
| `motor/datos/bcrp.py` | Riesgo país (EMBIG) e inflación (IPC Lima) |
| `motor/datos/tesoro.py` | Rf: bono del Tesoro a 10 años al cierre del año |
| `motor/navegador/` | `Navegador` (Playwright con cartel y resaltado) y `recorrer()` (recorrido completo) |
| `motor/metodologia.py` | `recolectar()` insumos → `calcular()` resultados + controles; `mostrar_calculos()` |
| `motor/excel/lienzo.py` | `LienzoVivo` (xlwings, animado) y `LienzoArchivo` (openpyxl): misma interfaz |
| `motor/excel/plantilla_wacc.py` | Las 10 hojas del modelo CPPC/EVA |
| `motor/generar.py` | Orquestador: recorrido → insumos → cálculo → Excel → verificación → evidencias |
| `motor/actualizador.py` | Consulta GitHub Releases y aplica la actualización |
| `scripts/registrar_mcp.py` | Registra el MCP en Claude Desktop, Codex y Antigravity |

## Cómo agregar un módulo nuevo (ej. flujo de caja descontado)
1. **Datos**: si necesitas una fuente nueva, crea `motor/datos/<fuente>.py` y devuelve objetos `Dato`
   usando `red.descargar(...)` (así queda en el registro de fuentes y en la caché).
2. **Metodología**: crea `motor/<modelo>.py` con `recolectar()` y `calcular()` que devuelvan un dict de resultados
   y una lista de controles `(nombre, ok, detalle)`.
3. **Plantilla Excel**: crea `motor/excel/plantilla_<modelo>.py` con `construir(L, insumos, resultados)` usando
   solo los métodos del lienzo (`L.paso`, `L.escribir`, `L.fila`, `L.enlace`…). Funcionará en vivo y en archivo.
4. **Orquestador**: agrega `generar_<modelo>()` en `motor/generar.py` (copia la estructura de `generar_wacc`).
5. **Interfaces**: una herramienta `@mcp.tool()` en `mcp_server/server.py`, un endpoint en `web/app.py`
   y, si quieres, una pestaña en el panel.
6. **Pruebas**: un caso validado en `tests/` (idealmente contra un Excel resuelto a mano).
7. Sube `VERSION`, anota en `CHANGELOG.md` y publica (ver abajo).

## Publicar una versión
```bash
# 1. cambia VERSION (ej. 0.3.0) y CHANGELOG.md
git commit -am "FinPerú 0.3.0"
git tag v0.3.0
git push && git push --tags
```
La acción `.github/workflows/release.yml` arma `FinPeru-v0.3.0.zip` (con `uv.exe` incluido) y crea el Release.
Las instalaciones existentes verán el aviso de actualización en el panel.

Para armar el zip localmente: `python scripts/empaquetar.py` → `dist/FinPeru-vX.Y.Z.zip`.

## Qué nunca toca el actualizador
`.venv/`, `datos_cache/`, `salidas/`, `_analisis/`, `plantillas/_fuente_curso/`, `config.local.json`.
Si agregas una carpeta de código nueva en la raíz, añádela a `CARPETAS_CODIGO` en `motor/actualizador.py`.
