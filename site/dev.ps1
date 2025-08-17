# Start the Astro dev server from the site folder consistently
# Usage: From repo root or anywhere, run:
#   powershell -ExecutionPolicy Bypass -File "site\dev.ps1"

param(
  [int]$Port = 4321
)

Set-Location -LiteralPath (Join-Path $PSScriptRoot '.')
Write-Host "Starting Astro dev server in: $(Get-Location) on port $Port"
$env:PORT = $Port
npm run dev
