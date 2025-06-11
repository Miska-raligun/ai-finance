# PowerShell deployment script for Windows
$ErrorActionPreference = 'Stop'

# === Backend Setup ===
Push-Location backend
if (-Not (Test-Path 'venv')) {
    Write-Host '[backend] Creating virtual environment...'
    python -m venv venv
}
.\venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
$env:FLASK_APP = 'app.py'
$backendProc = Start-Process 'waitress-serve' '--host=0.0.0.0 --port=5000 app:app' -NoNewWindow -PassThru
deactivate
Pop-Location

# === Frontend Setup ===
Push-Location frontend
if (-Not (Test-Path 'node_modules')) {
    Write-Host '[frontend] Installing node dependencies...'
    npm install
}
$frontendProc = Start-Process 'npm' 'run dev' -NoNewWindow -PassThru
Pop-Location

Write-Host 'Servers started. Press Ctrl+C to stop...'
try {
    Wait-Process -Id $backendProc.Id, $frontendProc.Id
} finally {
    if ($backendProc -and !$backendProc.HasExited) { Stop-Process -Id $backendProc.Id }
    if ($frontendProc -and !$frontendProc.HasExited) { Stop-Process -Id $frontendProc.Id }
}
