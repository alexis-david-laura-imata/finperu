# Cambios

## 0.2.1 — 2026-11-08
- **Corregido**: bancos y otras empresas financieras (p.ej. BANCO BBVA PERU) fallaban con
  "unsupported operand type(s) for +: 'NoneType' and 'NoneType'". La SMV usa planes de cuentas distintos
  según el tipo de empresa; ahora FinPerú reconoce los planes D (general), F (bancos, financieras, cajas),
  E (seguros), A (AFP), I (agentes de bolsa) y V (CAVALI/BVL), y busca por descripción si aparece otro.
  Validado con las 351 presentaciones anuales 2025 y las 367 de 2023 del servicio de la SMV.
- Bancos: la deuda financiera (D) son los adeudos y obligaciones financieras (los depósitos son pasivo
  operativo); el Kd aproximado usa los intereses de adeudos (cuenta 2F0404 del estado individual) y se
  muestra un aviso sobre cómo interpretar el WACC de un banco.
- Mensajes de error claros: si falta una cifra se dice cuál; si falta una librería se indica cómo instalarla.
- `FinPeru.bat` revisa al abrir que estén todas las librerías (p.ej. `pdfplumber`) e instala las que falten.
- Nuevo control "Kd mayor que cero". Pruebas nuevas con casos reales de cada plan de cuentas.

## 0.2.0 — 2026-11-07
Primera versión distribuible.

- **Navegación autónoma**: recorre la SMV (descarga el PDF auditado y el XBRL), Damodaran (archivo histórico
  del año evaluado), el Tesoro de EE.UU. y el BCRP, resaltando en pantalla dónde hace clic.
- **Kd automático desde el PDF auditado**: localiza la nota de "Otros pasivos financieros", lee tipo, banco,
  tasa, corriente y no corriente, y comprueba que cuadre con el estado de situación.
- **Opciones de visualización**: todo el proceso, solo Excel, solo descargas, solo cálculos en Python o nada;
  con control de velocidad.
- **Instalador de un clic** con Python privado (uv), Chromium y registro MCP en Claude Desktop, Codex y Antigravity.
- **Actualizaciones automáticas** desde GitHub Releases, con respaldo y sin tocar los datos del usuario.
- Menú `FinPeru.bat`, acceso directo con ícono, documentación (manual y arquitectura).

## 0.1.0
- Motor WACC/EVA validado contra los casos del curso (Laive 2021 y 2023).
- Panel web local accesible, servidor MCP, Excel en vivo (xlwings) o en archivo (openpyxl), controles y fuentes.
