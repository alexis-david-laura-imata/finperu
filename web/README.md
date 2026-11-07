# Panel web — guía para rediseñarlo

El panel tiene tres capas. **Para cambiar el diseño solo necesitas tocar `static/`.**

```
web/
  app.py            API (FastAPI). No tiene lógica financiera: solo llama al motor.
  static/
    index.html      estructura (HTML semántico, accesible)
    styles.css      diseño (todo sale de las variables de :root)
    app.js          comportamiento (llama a la API; sin librerías ni compilación)
```

Iniciar: `python scripts\panel.py` → http://127.0.0.1:8765 (solo accesible desde tu PC).
Sin internet o para pruebas: `$env:FINPERU_VIA_SMV="espejo"` antes de iniciar.

## Contrato de la API (no cambia aunque cambies el diseño)

| Método | Ruta | Para qué | Respuesta |
|---|---|---|---|
| GET | `/api/estado` | versión, si hay Excel en vivo, si está ocupado | `{version, excel_vivo, sistema, salidas, ocupado}` |
| GET | `/api/empresas?q=laive` | buscar empresa (nombre, RUC o RPJ) | `[{rpj, ruc, nombre, ciiu, sector, tipo_empresa, primer_periodo, ultimo_periodo, industria_sugerida}]` |
| GET | `/api/industrias?region=emerg` | lista de industrias Damodaran | `["Food Processing", ...]` |
| GET | `/api/vista_previa?rpj=CI0011&anio=2023` | cifras clave SMV antes de generar | `{tipo_estados, conceptos, conceptos_anterior, deuda_financiera, cuadra, fuente}` |
| POST | `/api/kd_pdf` | lee la nota de deuda del PDF auditado (descarga desde la SMV) | `{encontrada, pagina, lineas, kd_pdf, cuadra, avisos}` |
| POST | `/api/kd_pdf_subir` | igual, pero con un PDF subido (multipart: `archivo`, `rpj`, `anio`) | igual que arriba |
| POST | `/api/generar` | inicia la construcción (202) | `{id}` · 409 si ya hay una en curso |
| GET | `/api/trabajos/{id}` | estado del trabajo | `{estado: trabajando\|listo\|error, resultado?, error?}` |
| GET | `/api/eventos` | **Server-Sent Events** en vivo | cada mensaje: `{id, t, tipo, msg, ...}` |
| GET | `/api/historial` | modelos generados | `[{carpeta, empresa, anio, generado, wacc, eva, modo, controles_ok}]` |
| GET | `/api/modelos/{carpeta}/excel` | descargar el .xlsx | archivo |
| POST | `/api/modelos/{carpeta}/abrir?que=excel\|carpeta` | abrir en tu PC | `{abierto}` |
| GET | `/api/actualizacion` | ¿hay una versión nueva en GitHub? | `{actual, ultima, hay_actualizacion, notas}` |
| POST | `/api/actualizar` | descarga e instala la nueva versión | `{ok, mensaje, version?}` |

### Cuerpo de `POST /api/generar`
```json
{
  "rpj": "CI0011", "anio": 2023, "industria": "Food Processing",
  "modo": "vivo", "velocidad": 1.0,
  "ver_navegador": true, "ver_calculos": true,
  "kd_modo": "pdf",
  "kd_tabla": [{"tipo": "PRESTAMOS BANCARIOS", "entidad": "BCP", "tasa_min": 0.0355, "tasa_max": 0.0555,
                "corriente": 11027, "no_corriente": 15805, "moneda": "S/"}],
  "kd": null,
  "parametros": {"tasa_impuesto": 0.295, "damodaran_vintage": "cierre_siguiente",
                 "beta_columna": "Unlevered beta", "prima_promedio": "aritmetico", "region_beta": "emerg"},
  "sobrescribir": {"inflacion_pe": 0.0341}
}
```
Las tasas van en **decimal** (0.0525 = 5.25 %).
`kd_modo`: `pdf` (lee la nota del PDF auditado; lo que el panel usa por defecto), `tabla` (usa `kd_tabla`), `unico` (usa `kd`), `aproximado` (gastos financieros ÷ deuda, con aviso; es el valor por defecto de la API).

### Opciones de visualización (lo que el usuario elige ver)
| Preset | `modo` | `ver_navegador` | `ver_calculos` |
|---|---|---|---|
| Todo el proceso | vivo | true | true |
| Solo el Excel | vivo | false | false |
| Solo las descargas | archivo | true | false |
| Solo los cálculos en Python | archivo | false | true |
| Nada (rápido) | archivo | false | false |

`velocidad` multiplica las pausas: 0.5 = el doble de rápido, 2 = la mitad (ideal para grabar).

### Tipos de evento (`tipo`) útiles para animaciones
`inicio`, `descarga`, `descarga_ok`, `cache`, `reintento`, `aviso`, `smv`, `damodaran`, `bcrp`, `tesoro`,
`insumos_ok`, `resultado`, `excel`, `excel_paso` (mensaje "Paso N/10 · …"), `excel_ok`, `fin`,
`navegador` (pasos del recorrido web), `calculo` (trae `formula`, `sustitucion`, `resultado`), `kd_pdf`, `actualizar`.

## Accesibilidad que conviene conservar al rediseñar
- Cada campo tiene `<label for>`; los grupos de opciones usan `<fieldset><legend>`.
- El buscador es un *combobox* ARIA (flechas ↑↓, Enter, Escape).
- El registro en vivo es `role="log"` con `aria-live`; la barra de progreso usa `role="progressbar"`.
- Foco visible (`:focus-visible`), enlace "Saltar al contenido", respeto a `prefers-reduced-motion`,
  modo oscuro con `prefers-color-scheme`, contraste AA.
- Las tablas largas están en contenedores con scroll horizontal (`.tabla-desplazable`) para que en el celular no se desborde la página.
