$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (Test-Path -LiteralPath $venvPython) {
    $python = $venvPython
} else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        throw "Python was not found. Create .venv or install Python on PATH."
    }
    $python = $pythonCommand.Source
}

Push-Location $repoRoot
try {
    & $python -m ruff check .
    & $python scripts/check_architecture.py
    & $python scripts/check_test_doubles.py
    & $python -m pytest -q

    Push-Location (Join-Path $repoRoot "web\frontend")
    try {
        npm run lint
        npx tsc --noEmit
        npm test -- --run
        npm run build
    } finally {
        Pop-Location
    }
} finally {
    Pop-Location
}
