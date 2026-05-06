# VitaCall: backend + frontend in een commando.
#
# Backend draait op http://127.0.0.1:8000 (FastAPI via uvicorn).
# Frontend draait op http://127.0.0.1:5173 (Vite dev-server).
# Beide processen blijven open in hetzelfde venster zodat je live de logs ziet.
# Stop met Ctrl+C; beide processen worden netjes opgeruimd.
#
# Gebruik:
#   pwsh -File run.ps1            # default: dev-mode
#   pwsh -File run.ps1 -Mode prod # productie: docker compose up
#
# Vereisten: Python 3.11+, Node 20+, een getraind model in models/.
param(
    [ValidateSet('dev', 'prod')]
    [string]$Mode = 'dev'
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

if ($Mode -eq 'prod') {
    Write-Host "[run.ps1] productie-mode: docker compose up -d" -ForegroundColor Cyan
    Push-Location $root
    docker compose up -d
    Write-Host "API:        http://localhost:8000"
    Write-Host "MLflow UI:  http://localhost:5000"
    Write-Host "Prometheus: http://localhost:9090"
    Pop-Location
    return
}

# Backend in achtergrond-job, frontend in foreground.
$model = Join-Path $root 'models\sentiment_heavy.pkl'
if (-not (Test-Path $model)) {
    Write-Host "[run.ps1] Geen model gevonden. Run main.ipynb eerst (sectie 2)." -ForegroundColor Yellow
    exit 1
}

Write-Host "[run.ps1] backend starten op http://127.0.0.1:8000 ..." -ForegroundColor Cyan
$backend = Start-Process -PassThru -NoNewWindow -FilePath python -ArgumentList @(
    '-m', 'uvicorn', 'serve:app',
    '--host', '127.0.0.1',
    '--port', '8000'
) -WorkingDirectory $root

Start-Sleep -Seconds 2
try {
    Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 5 | Out-Null
    Write-Host "[run.ps1] backend OK" -ForegroundColor Green
} catch {
    Write-Host "[run.ps1] backend health-check faalde: $_" -ForegroundColor Red
    Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    exit 1
}

Write-Host "[run.ps1] frontend starten op http://127.0.0.1:5173 ..." -ForegroundColor Cyan
try {
    Push-Location (Join-Path $root 'electron')
    npm run dev
} finally {
    Pop-Location
    Write-Host "[run.ps1] backend stoppen ..." -ForegroundColor Cyan
    Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
}
