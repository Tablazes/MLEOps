# run.ps1 — start de cloud-backend (FastAPI) en de edge/operator-app in een commando.
#
# Gebruik vanuit de project-root:
#   ./run.ps1
#
# Start de cloud-service (serve:app via uvicorn) op de achtergrond, wacht tot
# /health gezond is, en opent daarna de web-frontend in de browser.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# serve_web.py start de backend (incl. /call/*-endpoints + web-mount), wacht op
# /health, en opent de browser. Dat is precies wat de frontend nodig heeft.
Write-Host "==> backend + web-frontend starten (serve_web.py op :8000)..."
python (Join-Path $root "serve_web.py")
