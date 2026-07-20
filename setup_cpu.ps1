$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root "runtime\python.exe"
Write-Host "FaceFinder CPU diagnostics" -ForegroundColor Cyan
if (-not (Test-Path $Python)) {
    Write-Host "The bundled runtime is missing. Run FaceFinder_Setup.exe again to repair the installation." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}
& $Python (Join-Path $Root "portable_check.py")
Read-Host "Press Enter to close"
