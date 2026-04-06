# start.ps1 - Levanta toda la plataforma Glucose Intelligence
# Orden: FastAPI (dueño de DuckDB) -> Monitor (escribe via API) -> Streamlit
# Uso: .\start.ps1

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = "$root\.venv\Scripts\Activate.ps1"
$python = "$root\.venv\Scripts\python.exe"

Write-Host "Glucose Intelligence Platform - Iniciando servicios..." -ForegroundColor Cyan

# Verificar que el venv existe
if (-not (Test-Path $python)) {
    Write-Host "  ERROR: Virtualenv no encontrado en $root\.venv" -ForegroundColor Red
    Write-Host "  Crea el venv con: python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

# Activar venv en esta sesion para el paso de importacion CSV
& $venv

# Limpiar procesos previos en los puertos
Write-Host "  Limpiando puertos 8888 y 8501..." -ForegroundColor DarkGray
$ports = @(8888, 8501)
foreach ($port in $ports) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $conns) {
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "    Matado PID $($conn.OwningProcess) en puerto $port" -ForegroundColor DarkYellow
    }
}
Start-Sleep -Seconds 2

# 0. Importar CSVs de LibreView (antes de FastAPI, DuckDB single-writer)
$csvDir = "$root\Examenes_resultados"
$csvFiles = Get-ChildItem -Path $csvDir -Filter "*.csv" -ErrorAction SilentlyContinue
if ($null -ne $csvFiles -and $csvFiles.Count -gt 0) {
    Write-Host "  [0/3] Importando $($csvFiles.Count) CSV(s) de LibreView..." -ForegroundColor Yellow
    foreach ($csv in $csvFiles) {
        Write-Host "    -> $($csv.Name)" -ForegroundColor DarkYellow
        # Usar python.exe del venv directamente para evitar bloqueo de AppLocker
        & $python "$root\scripts\import_history.py" --csv $csv.FullName
    }
    Write-Host "  Importacion completada." -ForegroundColor Yellow
    Write-Host ""
} else {
    Write-Host "  [0/3] Sin CSVs en Examenes_resultados/" -ForegroundColor DarkGray
}

# 1. FastAPI (unico proceso que toca DuckDB)
# Usa python -m uvicorn para evitar bloqueo de AppLocker sobre uvicorn.exe
Write-Host "  [1/3] Arrancando FastAPI (DuckDB)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; & '$venv'; & '$python' -m uvicorn api.main:app --port 8888 --reload" -WindowStyle Normal

Start-Sleep -Seconds 5

# 2. Monitor de polling (escribe via POST /api/readings)
Write-Host "  [2/3] Arrancando Monitor (LibreLinkUp -> API)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; & '$venv'; & '$python' monitor/monitor_glucose.py" -WindowStyle Normal

Start-Sleep -Seconds 8

# 3. Streamlit dashboard (lee FastAPI)
# Usa python -m streamlit para evitar bloqueo de AppLocker sobre streamlit.exe
Write-Host "  [3/4] Arrancando Streamlit..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; & '$venv'; & '$python' -m streamlit run dashboard/app.py --server.port 8501" -WindowStyle Normal

Start-Sleep -Seconds 3

# 4. Bot de Telegram bidireccional (chat con IA)
Write-Host "  [4/4] Arrancando Telegram Bot..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; & '$venv'; & '$python' -m telegram_bot.bot" -WindowStyle Normal

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "Servicios iniciados:" -ForegroundColor Green
Write-Host "  FastAPI       : http://localhost:8888/docs   (DuckDB owner)" -ForegroundColor Green
Write-Host "  Monitor       : LibreLinkUp -> POST API cada 2 min" -ForegroundColor Green
Write-Host "  Dashboard     : http://localhost:8501" -ForegroundColor Green
Write-Host "  Telegram Bot  : escuchando mensajes (chat directo con IA)" -ForegroundColor Green
Write-Host ""
Write-Host "Para re-importar CSVs sin reiniciar:" -ForegroundColor Cyan
Write-Host "  -> Boton 'Importar CSVs' en el sidebar del dashboard" -ForegroundColor Cyan
Write-Host "  -> O: POST http://localhost:8888/api/admin/import-csv" -ForegroundColor Cyan
Write-Host ""
Write-Host "NOTA: Los CSVs de LibreView solo incluyen datos sincronizados a la nube." -ForegroundColor Yellow
Write-Host "  Si el dashboard muestra datos antiguos, abre LibreLink en el telefono" -ForegroundColor Yellow
Write-Host "  para sincronizar, luego exporta un CSV nuevo y usa el boton Importar." -ForegroundColor Yellow
