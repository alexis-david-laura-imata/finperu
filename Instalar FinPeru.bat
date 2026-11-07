@echo off
title FinPeru - instalador
cd /d "%~dp0"
echo.
echo  Instalando FinPeru. Puede tardar entre 3 y 10 minutos la primera vez
echo  (descarga Python, librerias y el navegador). No cierres esta ventana.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalador\instalar.ps1" %*
echo.
pause
