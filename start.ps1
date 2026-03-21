# start.ps1 - Levanta toda la plataforma Glucose Intelligence
# Orden: FastAPI (dueño de DuckDB) -> Monitor (escribe via API) -> Streamlit
# Uso: .\start.ps1

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = "$root\.venv\Scripts\Activate.ps1"

Write-Host "Glucose Intelligence Platform - Iniciando servicios..." -ForegroundColor Cyan

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

# 1. FastAPI (unico proceso que toca DuckDB)
Write-Host "  [1/3] Arrancando FastAPI (DuckDB)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; & '$venv'; uvicorn api.main:app --port 8888 --reload" -WindowStyle Normal

Start-Sleep -Seconds 5

# 2. Monitor de polling (escribe via POST /api/readings)
Write-Host "  [2/3] Arrancando Monitor (LibreLinkUp -> API)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; & '$venv'; python monitor/monitor_glucose.py" -WindowStyle Normal

Start-Sleep -Seconds 8

# 3. Streamlit dashboard (lee FastAPI)
Write-Host "  [3/3] Arrancando Streamlit..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; & '$venv'; streamlit run dashboard/app.py --server.port 8501" -WindowStyle Normal

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "Servicios iniciados:" -ForegroundColor Green
Write-Host "  FastAPI   : http://localhost:8888/docs   (DuckDB owner)" -ForegroundColor Green
Write-Host "  Monitor   : LibreLinkUp -> POST API cada 2 min" -ForegroundColor Green
Write-Host "  Dashboard : http://localhost:8501" -ForegroundColor Green
