# PowerShell Wrapper for ProceduralAnimation Unified Test Runner (Task 6G-D-PRE-P1)
# Usage:
#   .\run_tests.ps1 -tier quick
#   .\run_tests.ps1 -tier physics
#   .\run_tests.ps1 -tier motion
#   .\run_tests.ps1 -tier full
#   .\run_tests.ps1 -test-id spatial_layout_clearance

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Locate valid Python interpreter (avoiding zero-byte Windows Store alias)
$pythonExe = $null
$candidates = @(
    "C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe",
    "C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe",
    "C:\Program Files\Python314\python.exe",
    "C:\Program Files\Python312\python.exe",
    "C:\Users\64701\AppData\Local\Python\bin\python.exe"
)

foreach ($c in $candidates) {
    try {
        if (Test-Path $c -ErrorAction SilentlyContinue) {
            $pythonExe = $c
            break
        }
    } catch {
        # Continue searching
    }
}

if (-not $pythonExe) {
    $cmdPython = Get-Command python -ErrorAction SilentlyContinue
    if ($cmdPython -and ($cmdPython.Source -notmatch "WindowsApps")) {
        $pythonExe = $cmdPython.Source
    }
}

if (-not $pythonExe) {
    Write-Error "[ERROR] Valid Python executable not found."
    exit 1
}

$testRunnerScript = Join-Path $scriptDir "tests\run_test_suite.py"

Write-Host "Executing Unified Test Suite via: $pythonExe" -ForegroundColor Cyan
& $pythonExe -u $testRunnerScript @args

$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-Host "`nTest Suite finished with FAILURE (Exit Code: $exitCode)." -ForegroundColor Red
    exit $exitCode
} else {
    Write-Host "`nTest Suite finished with SUCCESS." -ForegroundColor Green
    exit 0
}
