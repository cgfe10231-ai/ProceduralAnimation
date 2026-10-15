# PowerShell script to trigger the procedural animation pipeline
$ErrorActionPreference = "Stop"

$blenderPath = "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
if (-not (Test-Path $blenderPath)) {
    Write-Error "Blender executable not found at: $blenderPath"
    exit 1
}

Write-Host "Starting Procedural Animation Pipeline..." -ForegroundColor Cyan
& $blenderPath -b -P run_pipeline.py

if ($LASTEXITCODE -ne 0) {
    Write-Error "Pipeline failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}
Write-Host "Pipeline execution succeeded." -ForegroundColor Green
