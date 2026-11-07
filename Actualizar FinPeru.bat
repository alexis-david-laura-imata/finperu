@echo off
chcp 65001 >nul
title FinPeru - actualizar
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist ".venv\Scripts\python.exe" (
  echo FinPeru no esta instalado. Ejecuta primero "Instalar FinPeru.bat".
  pause & exit /b 1
)
".venv\Scripts\python.exe" -m motor.actualizador
pause
