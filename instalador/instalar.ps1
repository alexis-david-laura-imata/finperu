# FinPerú - instalador para Windows (no necesita permisos de administrador)
#
# Qué hace, en orden:
#   1. Descarga "uv" (gestor de Python) a instalador\bin si no está.
#   2. Instala un Python 3.12 privado dentro de la carpeta de FinPerú (no toca tu sistema).
#   3. Crea el entorno .venv e instala las librerías de requirements.txt.
#   4. Descarga el navegador Chromium que usa el módulo de navegación.
#   5. Revisa si hay Microsoft Excel (para ver el Excel construirse en vivo).
#   6. Corre una prueba rápida.
#   7. Registra el servidor MCP en Claude Desktop, Codex y Antigravity (si están instalados).
#   8. Crea el acceso directo "FinPerú" en el escritorio y en el menú Inicio.
#
# Se puede ejecutar varias veces: lo que ya está bien instalado se reutiliza.

param(
    [switch]$SinAccesoDirecto,
    [switch]$SinMCP,
    [switch]$SinNavegador
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

$Raiz = Split-Path -Parent $PSScriptRoot
Set-Location $Raiz
$Bin = Join-Path $PSScriptRoot 'bin'
$Uv = Join-Path $Bin 'uv.exe'
$VenvPy = Join-Path $Raiz '.venv\Scripts\python.exe'
$Log = Join-Path $Raiz 'instalacion.log'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot 'python'   # Python privado dentro de FinPerú
$env:UV_LINK_MODE = 'copy'                                        # evita avisos en OneDrive
$env:PYTHONIOENCODING = 'utf-8'

"==== Instalación $(Get-Date -Format s) ====" | Out-File $Log -Encoding utf8

function Paso($n, $texto) { Write-Host ""; Write-Host "[$n/8] $texto" -ForegroundColor Cyan }
function Ok($texto)       { Write-Host "      OK  $texto" -ForegroundColor Green }
function Aviso($texto)    { Write-Host "      !   $texto" -ForegroundColor Yellow }
function Ejecutar($exe, [string[]]$argumentos) {
    # PowerShell 5.1 convierte el stderr de programas externos en errores; aquí solo cuenta el código de salida
    $ErrorActionPreference = 'Continue'
    "`n> $exe $($argumentos -join ' ')" | Out-File $Log -Append -Encoding utf8
    & $exe @argumentos 2>&1 | Tee-Object -FilePath $Log -Append | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Falló: $exe $($argumentos -join ' ') (código $LASTEXITCODE). Detalle en instalacion.log" }
}

Write-Host ""
Write-Host "  == FinPerú · instalador ==" -ForegroundColor White
Write-Host "  Carpeta: $Raiz"
Write-Host "  Versión: $(Get-Content (Join-Path $Raiz 'VERSION') -ErrorAction SilentlyContinue)"

try {
    # 1 ------------------------------------------------------------------ uv
    Paso 1 'Gestor de Python (uv)'
    if (-not (Test-Path $Uv)) {
        New-Item -ItemType Directory -Force -Path $Bin | Out-Null
        $zip = Join-Path $env:TEMP 'uv-finperu.zip'
        $url = 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip'
        Write-Host "      Descargando uv desde GitHub…"
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
        $tmp = Join-Path $env:TEMP 'uv-finperu'
        if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
        Get-ChildItem $tmp -Recurse -Include 'uv.exe','uvx.exe' | Copy-Item -Destination $Bin -Force
        Remove-Item $zip, $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
    Ok "$(& $Uv --version)"

    # 2-3 ---------------------------------------------------------------- Python + librerías
    Paso 2 'Python privado y entorno .venv'
    $sano = $false
    if (Test-Path $VenvPy) {
        $ErrorActionPreference = 'Continue'
        & $VenvPy -c "import sys; assert sys.version_info >= (3, 11)" 2>$null
        $sano = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = 'Stop'
    }
    if ($sano) {
        Ok "Reutilizo el entorno existente ($(& $VenvPy --version))"
    } else {
        if (Test-Path (Join-Path $Raiz '.venv')) {
            Aviso 'El .venv existente no sirve; lo vuelvo a crear.'
            Remove-Item (Join-Path $Raiz '.venv') -Recurse -Force
        }
        Ejecutar $Uv @('python', 'install', '3.12')
        Ejecutar $Uv @('venv', '.venv', '--python', '3.12')
        Ok "Entorno creado ($(& $VenvPy --version))"
    }

    Paso 3 'Librerías (pandas, openpyxl, xlwings, playwright, mcp, fastapi…)'
    Ejecutar $Uv @('pip', 'install', '--python', $VenvPy, '-r', 'requirements.txt')
    Ok 'Librerías instaladas'

    # 4 ------------------------------------------------------------------ Chromium
    Paso 4 'Navegador para el módulo de descargas (Chromium)'
    if ($SinNavegador) { Aviso 'Omitido por parámetro -SinNavegador' }
    else {
        Ejecutar $VenvPy @('-m', 'playwright', 'install', 'chromium')
        Ok 'Chromium listo'
    }

    # 5 ------------------------------------------------------------------ Excel
    Paso 5 'Microsoft Excel'
    if (Test-Path 'Registry::HKEY_CLASSES_ROOT\Excel.Application') {
        Ok 'Excel encontrado: podrás ver el modelo construirse en vivo'
    } else {
        Aviso 'No encontré Excel. FinPerú igual funciona: genera el .xlsx sin animación.'
    }

    # 6 ------------------------------------------------------------------ prueba
    Paso 6 'Prueba rápida'
    Ejecutar $VenvPy @('-c', 'import motor, motor.generar, web.app, mcp; print("FinPeru", motor.__version__, "importa correctamente")')
    Ok 'El motor carga sin errores'

    # 7 ------------------------------------------------------------------ MCP
    Paso 7 'Conexión con asistentes de IA (Claude Desktop, Codex, Antigravity)'
    if ($SinMCP) { Aviso 'Omitido por parámetro -SinMCP' }
    else { Ejecutar $VenvPy @('scripts\registrar_mcp.py') }

    # 8 ------------------------------------------------------------------ accesos directos
    Paso 8 'Acceso directo'
    if ($SinAccesoDirecto) { Aviso 'Omitido por parámetro -SinAccesoDirecto' }
    else {
        $shell = New-Object -ComObject WScript.Shell
        $destinos = @(
            [Environment]::GetFolderPath('Desktop'),
            [Environment]::GetFolderPath('Programs')
        )
        foreach ($d in $destinos) {
            if (-not $d -or -not (Test-Path $d)) { continue }
            $lnk = $shell.CreateShortcut((Join-Path $d 'FinPerú.lnk'))
            $lnk.TargetPath = Join-Path $Raiz 'FinPeru.bat'
            $lnk.WorkingDirectory = $Raiz
            $lnk.IconLocation = (Join-Path $PSScriptRoot 'finperu.ico') + ',0'
            $lnk.Description = 'FinPerú - modelos financieros auditables'
            $lnk.Save()
            Ok "Acceso directo en $d"
        }
    }

    Write-Host ""
    Write-Host "  [OK] FinPerú quedó instalado." -ForegroundColor Green
    Write-Host "    - Abre 'FinPerú' desde el escritorio (o FinPeru.bat)."
    Write-Host "    - Si usas Claude Desktop, Codex o Antigravity: ciérralos por completo y ábrelos de nuevo."
    Write-Host ""
    exit 0
}
catch {
    Write-Host ""
    Write-Host "  [X] La instalación se detuvo: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "    Revisa instalacion.log en la carpeta de FinPerú. Puedes volver a ejecutar el instalador:" -ForegroundColor Red
    Write-Host "    lo que ya quedó bien se reutiliza." -ForegroundColor Red
    $_ | Out-File $Log -Append -Encoding utf8
    exit 1
}
