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

Write-Host '[backend] Starting Waitress on port 5000...'
$backendProc = Start-Process 'waitress-serve' '--host=0.0.0.0 --thread=4 --port=5000 app:app' -NoNewWindow -PassThru

Write-Host '[mcp] Starting MCP server on port 5001...'
$mcpProc = Start-Process 'python' 'mcp_server.py' -NoNewWindow -PassThru

Write-Host '[minimax-mcp] Starting MiniMax MCP server on port 5002...'
$minimaxMcpProc = Start-Process 'python' 'minimax_mcp_server.py' -NoNewWindow -PassThru

deactivate
Pop-Location

# === Frontend Setup ===
Push-Location frontend
if (-Not (Test-Path 'node_modules')) {
    Write-Host '[frontend] Installing Node.js dependencies...'
    npm install
}
Write-Host '[frontend] Starting Vite dev server...'
$frontendProc = Start-Process 'npm' 'run dev' -NoNewWindow -PassThru
Pop-Location

Write-Host ''
Write-Host '=========================================='
Write-Host '  Frontend     : http://localhost:5173'
Write-Host '  Backend      : http://localhost:5000'
Write-Host '  MCP SSE      : http://localhost:5001/mcp/sse'
Write-Host '  MiniMax MCP  : http://localhost:5002/mcp/sse'
Write-Host '=========================================='
Write-Host 'Press Ctrl+C to stop all services.'
Write-Host ''

# === Wait for all processes ===
try {
    Wait-Process -Id $backendProc.Id, $mcpProc.Id, $minimaxMcpProc.Id, $frontendProc.Id
} finally {
    if ($backendProc -and !$backendProc.HasExited) { Stop-Process -Id $backendProc.Id }
    if ($mcpProc    -and !$mcpProc.HasExited)     { Stop-Process -Id $mcpProc.Id }
    if ($minimaxMcpProc -and !$minimaxMcpProc.HasExited) { Stop-Process -Id $minimaxMcpProc.Id }
    if ($frontendProc -and !$frontendProc.HasExited) { Stop-Process -Id $frontendProc.Id }
}

