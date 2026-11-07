# Cambios

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
