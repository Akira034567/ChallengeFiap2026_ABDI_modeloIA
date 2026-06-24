$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:YOLO_CONFIG_DIR = Join-Path $PSScriptRoot "backend\data\ultralytics"
$env:MPLCONFIGDIR = Join-Path $PSScriptRoot "backend\data\matplotlib"
$env:KMP_DUPLICATE_LIB_OK = "TRUE"
$env:OMP_NUM_THREADS = "1"

function New-ProjectVenv {
  Write-Host "Criando ambiente virtual em .venv..."

  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    python -m venv .venv --upgrade-deps
    return
  }

  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    py -3.11 -m venv .venv --upgrade-deps
    return
  }

  throw "Python nao encontrado. Instale Python 3.11 e marque 'Add Python to PATH'."
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
  New-ProjectVenv
}

if (-not (Test-Path $venvPython)) {
  throw "Falha ao criar .venv. Verifique a instalacao do Python."
}

Write-Host "Garantindo pip dentro do .venv..."
& $venvPython -m ensurepip --upgrade
& $venvPython -m pip install --upgrade pip setuptools wheel

Write-Host "Instalando dependencias do backend..."
& $venvPython -m pip install -r "backend\requirements.txt"

Write-Host "Iniciando backend em http://localhost:8000 ..."
& $venvPython -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend
