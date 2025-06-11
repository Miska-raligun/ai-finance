# Build and package the entire desktop app (frontend + backend)
$ErrorActionPreference = 'Stop'

# === Frontend Build ===
Write-Host '[frontend] Building production files...'
Push-Location frontend

if (-Not (Test-Path 'node_modules')) {
    Write-Host '  Installing frontend dependencies (using npm mirror)...'
    npm install --registry=https://registry.npmmirror.com
}

npm run build
Pop-Location

# === Backend Build ===
Write-Host '[backend] Building executable...'
./build_windows.ps1

# === Copy frontend dist to electron app ===
Write-Host '[electron] Copying frontend build into packaging directory...'
$frontendDest = 'electron\frontend'
if (Test-Path $frontendDest) {
    Remove-Item -Recurse -Force $frontendDest
}
Copy-Item -Path 'frontend\dist' -Destination $frontendDest -Recurse

# === Electron Packaging ===
Write-Host '[electron] Installing dependencies and packaging...'
Push-Location electron

if (-Not (Test-Path 'node_modules')) {
    Write-Host '  Installing electron dependencies (using npm mirror)...'
    $env:ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"
    npm install --registry=https://registry.npmmirror.com
}

# 自动安装 electron-packager（如果未安装）
if (-Not (Test-Path '.\node_modules\electron-packager')) {
    Write-Host '  Installing electron-packager...'
    npm install electron-packager --save-dev
}

# 检查图标文件
$iconPath = "Anon.ico"
if (-Not (Test-Path $iconPath)) {
    Write-Warning "  ⚠️ .ico not found, EXE will use default Electron icon."
    $iconArg = ""
} else {
    $iconArg = "--icon=Anon.ico"
}

# 打包命令
npx electron-packager . ai-finance --overwrite $iconArg

Pop-Location

Write-Host ''
Write-Host '✅ Desktop package created in electron/ai-finance-win32-x64/'
Write-Host ''
