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
Write-Host '[frontend] Resetting node dependencies to avoid rollup errors...'

# 删除 node_modules 和 package-lock.json（如果存在）
if (Test-Path 'node_modules') {
    Remove-Item -Recurse -Force 'node_modules'
}
if (Test-Path 'package-lock.json') {
    Remove-Item -Force 'package-lock.json'
}

# 重新安装依赖
Write-Host '[frontend] Installing node dependencies...'
Start-Process "cmd.exe" -ArgumentList "/c npm install" -Wait -NoNewWindow

# 启动前端服务
$frontendProc = Start-Process "C:\Program Files\nodejs\npm.cmd" -ArgumentList "run dev" -NoNewWindow -PassThru
Pop-Location

# === Wait for both processes ===
Write-Host 'Servers started. Press Ctrl+C to stop...'
try {
    Wait-Process -Id $backendProc.Id, $frontendProc.Id
} finally {
    if ($backendProc -and !$backendProc.HasExited) { Stop-Process -Id $backendProc.Id }
    if ($frontendProc -and !$frontendProc.HasExited) { Stop-Process -Id $frontendProc.Id }
}

