$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root "runtime\python.exe"
Write-Host "FaceFinder GPU diagnostics" -ForegroundColor Cyan
Write-Host "The installer already bundles ONNX Runtime GPU, CUDA 12.4, cuDNN 9.1, cuFFT, cuRAND, NVJitLink and the VC++ prerequisite." -ForegroundColor Gray
if (-not (Test-Path $Python)) {
    Write-Host "The bundled runtime is missing. Run FaceFinder_Setup.exe again to repair the installation." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}
& $Python (Join-Path $Root "portable_check.py")
Write-Host ""
Write-Host "If CUDA does not activate, review runtime_status.json. The diagnostic now exits with an error when required CUDA DLLs are missing or CUDAExecutionProvider is not actually active." -ForegroundColor Yellow
Read-Host "Press Enter to close"
