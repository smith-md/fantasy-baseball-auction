# start-draft.ps1 — Launches backend, frontend, and starts a draft session

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# Config
$leagueId = "45zdadwuml34g0k7"
$season = 2026
$numTeams = 12
$pollInterval = 5
$backendUrl = "http://127.0.0.1:8001"
$frontendUrl = "http://localhost:5173"

Write-Host "=== Fantasy Baseball Auction Draft ===" -ForegroundColor Cyan
Write-Host ""

# 1. Start backend (uvicorn)
Write-Host "[1/3] Starting backend server..." -ForegroundColor Yellow
$backend = Start-Process -PassThru -NoNewWindow -FilePath "python" `
    -ArgumentList "-c `"import uvicorn; uvicorn.run('src.draft.api_server:app', host='127.0.0.1', port=8001, log_level='info')`"" `
    -WorkingDirectory $projectRoot

Write-Host "  Backend PID: $($backend.Id)"

# Wait for backend to be ready
Write-Host "  Waiting for backend..." -NoNewline
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $null = Invoke-RestMethod -Uri "$backendUrl/draft-session/status" -TimeoutSec 2 -ErrorAction Stop
        $ready = $true
        break
    } catch {
        Write-Host "." -NoNewline
    }
}
if ($ready) {
    Write-Host " Ready!" -ForegroundColor Green
} else {
    Write-Host " Timed out waiting for backend!" -ForegroundColor Red
    Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    exit 1
}

# 2. Start frontend (vite dev server)
Write-Host "[2/3] Starting frontend dev server..." -ForegroundColor Yellow
$frontend = Start-Process -PassThru -NoNewWindow -FilePath "cmd.exe" -ArgumentList "/c npm run dev" -WorkingDirectory "$projectRoot\frontend"
Write-Host "  Frontend PID: $($frontend.Id)"
Start-Sleep -Seconds 3

# 3. Start draft session
Write-Host "[3/3] Starting draft session..." -ForegroundColor Yellow
$body = @{
    league_id            = $leagueId
    season               = $season
    num_teams            = $numTeams
    poll_interval_seconds = $pollInterval
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Uri "$backendUrl/draft-session/start" `
        -Method Post `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 120
    Write-Host "  Session started: $($response.message)" -ForegroundColor Green
} catch {
    $status = $_.Exception.Response.StatusCode.value__
    if ($status -eq 409) {
        Write-Host "  Session already active (resuming)" -ForegroundColor Yellow
    } else {
        Write-Host "  Failed to start session: $_" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=== Draft is running ===" -ForegroundColor Cyan
Write-Host "  Frontend: $frontendUrl"
Write-Host "  Backend:  $backendUrl"
Write-Host ""
Write-Host "Press Ctrl+C to shut down." -ForegroundColor DarkGray

# Wait and cleanup on exit
try {
    while ($true) { Start-Sleep -Seconds 5 }
} finally {
    Write-Host ""
    Write-Host "Shutting down..." -ForegroundColor Yellow
    Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue
    # Kill any orphaned node processes from vite
    Get-Process -Name "node" -ErrorAction SilentlyContinue |
        Where-Object { $_.MainModule.FileName -like "*fantasy-baseball*" } |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "Done." -ForegroundColor Green
}
