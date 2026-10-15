# PowerShell wrapper to run Task 1 validation suite
$ErrorActionPreference = "Stop"

$blenderPath = "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
if (-not (Test-Path $blenderPath)) {
    Write-Error "Blender not found at $blenderPath"
    exit 1
}

Write-Host "Running Task 1 validation via Blender Python..." -ForegroundColor Cyan
& $blenderPath -b --python tests/run_validation.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "Validation failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}
Write-Host "Task 1 validation suite completed successfully." -ForegroundColor Green
