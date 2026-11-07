@echo off
chcp 65001 >nul
title FinPeru
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
set PYTHONIOENCODING=utf-8
if not exist "%PY%" (
  echo FinPeru aun no esta instalado. Iniciando el instalador...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalador\instalar.ps1"
  if not exist "%PY%" ( pause & exit /b 1 )
)
if /i "%~1"=="panel" goto panel

:menu
cls
echo.
echo   ==========================================
echo     FinPeru  -  modelos financieros auditables
echo   ==========================================
echo.
echo     1. Abrir el panel web (recomendado)
echo     2. Demo en vivo (navegador + Excel + calculos)
echo     3. Buscar actualizaciones
echo     4. Conectar con Claude / Codex / Antigravity
echo     5. Diagnostico de fuentes de datos
echo     6. Salir
echo.
set "op="
set /p op="  Elige una opcion y pulsa Enter: "
if "%op%"=="1" goto panel
if "%op%"=="2" goto demo
if "%op%"=="3" goto actualizar
if "%op%"=="4" goto mcp
if "%op%"=="5" goto diagnostico
if "%op%"=="6" exit /b 0
goto menu

:panel
echo.
echo  Abriendo http://127.0.0.1:8765 ... (cierra esta ventana para detener FinPeru)
"%PY%" scripts\panel.py
pause
goto menu

:demo
echo.
set "emp="
set /p emp="  Empresa (Enter = Laive): "
if "%emp%"=="" set "emp=Laive"
set "anio="
set /p anio="  Anio (Enter = 2023): "
if "%anio%"=="" set "anio=2023"
set "extra="
if /i not "%emp%"=="Laive" set "extra=--industria-auto"
"%PY%" scripts\demo.py --empresa "%emp%" --anio %anio% --ver todo %extra%
pause
goto menu

:actualizar
"%PY%" -m motor.actualizador
pause
goto menu

:mcp
"%PY%" scripts\registrar_mcp.py
pause
goto menu

:diagnostico
"%PY%" scripts\probar_fuentes.py
pause
goto menu
