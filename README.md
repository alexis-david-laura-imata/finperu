# FinPerú

**Modelos financieros auditables de empresas peruanas, construidos en Excel ante tus ojos.**

FinPerú descarga por sí solo los estados financieros de la **SMV**, las betas y primas de **Damodaran**,
el riesgo país y la inflación del **BCRP** y la tasa libre de riesgo del **Tesoro de EE.UU.**; lee la nota
de deuda del **PDF auditado** para calcular el Kd, y arma un Excel con el **CPPC/WACC, ROIC y EVA** donde
cada número tiene fórmula viva, nota con su fuente y control de cuadre.

Funciona de tres formas: con su **panel web** (sin IA), desde la **línea de comandos**, o conectado a
**Claude Desktop, Codex o Antigravity** como servidor MCP ("hazme el WACC de Gloria 2024").

## Instalación (Windows 10/11)

1. Descarga el último `FinPeru-vX.Y.Z.zip` de [Releases](https://github.com/alexis-david-laura-imata/finperu/releases/latest) y descomprímelo
   en una carpeta tuya (por ejemplo `Documentos\FinPeru`).
2. Haz doble clic en **`Instalar FinPeru.bat`**.

Eso es todo. El instalador **no necesita permisos de administrador ni que tengas Python**: trae su propio
Python dentro de la carpeta, instala las librerías y el navegador, registra FinPerú en los asistentes de IA
que tengas y crea el acceso directo **FinPerú** en el escritorio. La primera vez tarda de 3 a 10 minutos.

> ¿Prefieres Git? `git clone https://github.com/alexis-david-laura-imata/finperu` y luego `Instalar FinPeru.bat`.

## Uso

Abre **FinPerú** desde el escritorio y elige:

| Opción | Qué hace |
|---|---|
| 1. Panel web | Abre `http://127.0.0.1:8765`: buscas la empresa, eliges año e industria, y miras cómo se construye. |
| 2. Demo en vivo | Recorrido completo por consola: navegador + cálculos + Excel. Ideal para grabar. |
| 3. Actualizar | Descarga la última versión desde GitHub conservando tus modelos y datos. |
| 4. Conectar con IA | Vuelve a registrar el MCP en Claude Desktop, Codex y Antigravity. |
| 5. Diagnóstico | Prueba que la SMV, el BCRP, Damodaran y el Tesoro respondan. |

### Qué quieres ver mientras trabaja

| Modo | Navegador descargando | Excel construyéndose | Cálculos en Python |
|---|:-:|:-:|:-:|
| Todo el proceso | ✓ | ✓ | ✓ |
| Solo el Excel | | ✓ | |
| Solo las descargas | ✓ | | |
| Solo los cálculos | | | ✓ |
| Nada (rápido) | | | |

Y un control de **velocidad** (0 = sin pausas, 1 = normal, 2–3 = lento) para presentaciones o grabaciones.

### Con un asistente de IA
Después de instalar, cierra y vuelve a abrir tu asistente. Prueba:
- *"Busca Alicorp en FinPerú y genera su WACC 2024 mostrándome todo el proceso."*
- *"Lee la nota de deuda del PDF auditado de Gloria 2023 y dime el Kd."*

## Actualizaciones

FinPerú revisa GitHub y te avisa en el panel cuando hay una versión nueva. Al actualizar:
guarda una copia del código anterior en `datos_cache\respaldos\`, reemplaza solo el código y **nunca toca**
`salidas\`, `datos_cache\`, `.venv\` ni tus plantillas.

## Documentación
- [Manual de uso](docs/MANUAL.md)
- [Arquitectura y cómo agregar módulos](docs/ARQUITECTURA.md)
- [Metodología de cálculo](docs/metodologia_curso.yaml)
- [Guía para rediseñar el panel](web/README.md)
- [Cambios por versión](CHANGELOG.md)

## Fuentes y atribución
- **SMV** — Servicio de datos abiertos de información financiera y portal de información financiera (EEFF auditados).
  Espejo alternativo: base [smv-eeff](https://github.com/AtlasLedger/smv-eeff) (ODbL).
- **Aswath Damodaran**, NYU Stern — *Data: Current* y *Archives*.
- **BCRP** — Series estadísticas (PN01129XM EMBIG Perú, PN01273PM IPC Lima).
- **U.S. Department of the Treasury** — Daily Treasury Par Yield Curve Rates.

Cada archivo descargado queda registrado con su URL, fecha y hash SHA-256 en `datos_cache\registro_fuentes.jsonl`
y en la hoja *Fuentes* del Excel.

## Aviso
FinPerú es una herramienta académica y de apoyo. Los resultados dependen de las fuentes públicas y de los
supuestos elegidos; revisa la hoja *Controles* y las notas antes de usarlos para decisiones. No es asesoría financiera.

Licencia [MIT](LICENSE) · © 2026 Alexis David Laura Imata
