# Manual de FinPerú

## 1. Instalar
1. Descomprime `FinPeru-vX.Y.Z.zip` en una carpeta tuya. Evita carpetas del sistema como `Archivos de programa`.
2. Doble clic en **`Instalar FinPeru.bat`**. Se abre una ventana que muestra 8 pasos:

| Paso | Qué hace | Si falla |
|---|---|---|
| 1 | Descarga `uv`, el gestor de Python | Revisa tu internet o el antivirus; vuelve a ejecutar |
| 2 | Instala un Python 3.12 **privado** en `instalador\python` | Igual que arriba |
| 3 | Instala las librerías en `.venv` | Mira `instalacion.log` |
| 4 | Descarga Chromium (para el navegador automático) | Puedes saltarlo: `instalador\instalar.ps1 -SinNavegador` |
| 5 | Busca Microsoft Excel | Sin Excel igual funciona, sin animación |
| 6 | Prueba que el motor cargue | Mira `instalacion.log` |
| 7 | Registra FinPerú en Claude Desktop, Codex y Antigravity | Solo los que tengas instalados |
| 8 | Crea el acceso directo **FinPerú** | — |

Puedes ejecutar el instalador las veces que quieras: reutiliza lo que ya está bien.

## 2. El panel web
Abre **FinPerú → 1. Panel web**. Se abre `http://127.0.0.1:8765` (solo es visible desde tu PC).

1. **Empresa**: escribe el nombre, RUC o código SMV (por ejemplo "gloria"). Usa ↑↓ y Enter.
2. **Año**: el ejercicio a evaluar. FinPerú usa los estados consolidados y, si no existen, los individuales (te avisa).
3. **Industria Damodaran**: se sugiere sola según el CIIU de la empresa; cámbiala si no corresponde.
4. **Vista previa**: muestra las cifras clave de la SMV para que confirmes antes de generar.
5. **Costo de la deuda (Kd)**:
   - *Leer el PDF auditado* (recomendado): FinPerú descarga los EEFF auditados de la SMV, encuentra la nota de
     "Otros pasivos financieros" y arma la tabla de bancos y tasas. Revisa la tabla: las filas en naranja piden revisión.
   - *Tabla manual*: llenas tú la tabla (o subes el PDF si lo tienes).
   - *Tasa única*: escribes un Kd.
   - *Aproximado*: gastos financieros ÷ deuda. Rápido pero impreciso (en Laive 2023 da 13.8 % contra 7.0 % de la nota).
6. **Qué ver** (*Todo / Solo Excel / Solo descargas / Solo cálculos / Nada*) y **velocidad**.
7. **Generar**. El registro en vivo muestra cada descarga, cada cálculo y cada paso del Excel.

Al final aparece el resumen (Ke, Kd, WACC, ROIC, EVA y controles) con botones para abrir el Excel o la carpeta.

## 3. El Excel que genera
| Hoja | Contenido |
|---|---|
| Portada | Empresa, año, resultados y estado de los controles |
| Parametros | Tasa de impuesto, criterio de betas, prima, etc. (celdas naranjas = supuestos editables) |
| EEFF | Cuentas de la SMV usadas, año actual y anterior |
| Kd | Tabla de deuda por tipo y banco, pesos y Kd ponderado |
| Mercado | Rf, prima, beta desapalancada, riesgo país, inflaciones |
| CPPC | Beta apalancada, Ke en dólares y soles, WACC |
| EVA | NOPAT, capital invertido promedio, ROIC, EVA |
| Controles | Cuadres: activo = pasivo + patrimonio, pesos = 1, deuda de la nota = deuda del balance… |
| Fuentes | URL, fecha y hash SHA-256 de cada archivo usado |
| Registro | Bitácora de la construcción |

Colores: **azul** = dato descargado, **naranja** = supuesto del usuario, **negro** = fórmula, **verde** = vínculo a otra hoja.
Cada dato tiene una nota (pasa el mouse) con su fuente exacta. Los nombres de rango (`WACC`, `Ke_Final`, `Kd_Prom`…)
permiten auditar con *Fórmulas → Administrador de nombres*.

Junto al Excel quedan `resultados.json`, `receta.json` (para regenerar el mismo modelo) y la carpeta `evidencias\`
con los archivos originales descargados (PDF auditado, XBRL, hojas de Damodaran, CSV del Tesoro).

## 4. Con un asistente de IA (Claude Desktop, Codex, Antigravity)
Tras instalar, **cierra por completo** el asistente y ábrelo. Verás las herramientas de *finperu*. Ejemplos:
- "Busca Alicorp en FinPerú y dame la vista previa 2024."
- "Genera el WACC de Gloria 2023 mostrándome el navegador y el Excel, a velocidad 2."
- "Lee la nota de deuda del PDF auditado de Laive 2023."
- "Lista los últimos modelos que generé."

Si el asistente no ve FinPerú: menú **FinPerú → 4. Conectar con IA** y reinicia el asistente.

## 5. Línea de comandos
```bat
.venv\Scripts\python.exe scripts\demo.py --empresa Gloria --anio 2023 --ver todo --velocidad 1.5 --industria-auto
.venv\Scripts\python.exe scripts\probar_fuentes.py
.venv\Scripts\python.exe scripts\probar_kd_pdf.py --visible
.venv\Scripts\python.exe -m motor.actualizador --solo-consultar
```

## 6. Actualizar
El panel muestra un aviso cuando hay versión nueva; también puedes usar **FinPerú → 3** o `Actualizar FinPeru.bat`.
Se respalda el código anterior en `datos_cache\respaldos\` y no se tocan `salidas\`, `datos_cache\`, `.venv\`
ni `config.local.json`.

## 7. Problemas comunes
| Síntoma | Solución |
|---|---|
| "SMV no responde" | El servicio de la SMV a veces cae. FinPerú usa el espejo smv-eeff automáticamente. |
| El Excel no se anima | Cierra cuadros de diálogo abiertos en Excel; o elige "Solo cálculos". |
| La nota de deuda no cuadra | Revisa las filas naranjas en la tabla Kd; puedes corregirlas a mano antes de generar. |
| OneDrive bloquea archivos | Pausa la sincronización o instala FinPerú fuera de OneDrive. |
| Antivirus bloquea `uv.exe` | Agrega la carpeta de FinPerú como excepción y vuelve a instalar. |
