# Expose local Invoice API (port 8000) with a public Cloudflare URL.
# Keep this window open while others use the link.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\share_public_url.ps1

$ErrorActionPreference = "Stop"
$cloudflared = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
if (-not (Test-Path $cloudflared)) {
    $cloudflared = "C:\Program Files\cloudflared\cloudflared.exe"
}
if (-not (Test-Path $cloudflared)) {
    Write-Error "cloudflared not found. Install with: winget install Cloudflare.cloudflared"
}

$health = $null
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 3
} catch {
    Write-Host "API is not running on port 8000. Start it first:" -ForegroundColor Yellow
    Write-Host '  .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000'
    exit 1
}

Write-Host "Local API OK: $($health.status)" -ForegroundColor Green
Write-Host "Creating public tunnel (leave this window open)..." -ForegroundColor Cyan
& $cloudflared tunnel --protocol http2 --url http://127.0.0.1:8000
