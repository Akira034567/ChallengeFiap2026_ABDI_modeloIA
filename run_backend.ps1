$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:YOLO_CONFIG_DIR = Join-Path $PSScriptRoot "backend\data\ultralytics"
$env:MPLCONFIGDIR = Join-Path $PSScriptRoot "backend\data\matplotlib"
$env:KMP_DUPLICATE_LIB_OK = "TRUE"
$env:OMP_NUM_THREADS = "1"

if (-not (Test-Path ".venv")) {
  python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend


