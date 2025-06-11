# Build backend executable and prepare files for Electron packaging
$ErrorActionPreference = 'Stop'

# Ensure virtual environment
if (-Not (Test-Path 'backend\venv')) {
    python -m venv backend\venv
}
.\backend\venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r backend\requirements.txt

# Build executable
pyinstaller --onefile --name ai-finance-backend backend/app.py --hidden-import flask_cors --hidden-import waitress

$destDir = 'electron\backend'
if (-Not (Test-Path $destDir)) {
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
}

Copy-Item 'dist\ai-finance-backend.exe' $destDir -Force
if (Test-Path 'backend\.env') { Copy-Item 'backend\.env' $destDir -Force }
if (Test-Path 'backend\records.db') { Copy-Item 'backend\records.db' $destDir -Force }

deactivate
Write-Host 'Executable and data files copied to electron/backend'