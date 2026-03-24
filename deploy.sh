#!/bin/bash
set -e

echo "[start] Deploy script started..."

BACKEND_LOG="backend.log"
MCP_LOG="mcp.log"
MINIMAX_MCP_LOG="minimax_mcp.log"
FRONTEND_LOG="frontend.log"

# === Backend Setup ===
pushd backend >/dev/null

for PORT in 5000 5001 5002; do
  PID=$(lsof -ti:$PORT 2>/dev/null || true)
  if [ -n "$PID" ]; then
    echo "[backend] Port $PORT in use. Killing process $PID..."
    kill -9 $PID
  fi
done

if [ ! -d "venv" ]; then
  echo "[backend] Creating virtual environment..."
  python3 -m venv venv
fi

echo "[backend] Activating virtual environment..."
source venv/bin/activate

echo "[backend] Installing Python dependencies..."
pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 100
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 100

echo "[backend] Starting Waitress on port 5000..."
waitress-serve --host=0.0.0.0 --port=5000 app:app > "../$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
echo "[backend] Backend running (PID $BACKEND_PID)"

echo "[mcp] Starting MCP server on port 5001..."
python mcp_server.py > "../$MCP_LOG" 2>&1 &
MCP_PID=$!
echo "[mcp] MCP server running (PID $MCP_PID)"

echo "[minimax-mcp] Starting MiniMax MCP server on port 5002..."
python minimax_mcp_server.py > "../$MINIMAX_MCP_LOG" 2>&1 &
MINIMAX_MCP_PID=$!
echo "[minimax-mcp] MiniMax MCP server running (PID $MINIMAX_MCP_PID)"

deactivate
popd >/dev/null

# === Frontend Setup ===
cd frontend

if [ ! -d "node_modules" ]; then
  echo "[frontend] Installing Node.js dependencies..."
  npm install
fi

echo "[frontend] Starting Vite dev server..."
npm run dev > "../$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!
echo "[frontend] Frontend running (PID $FRONTEND_PID)"
cd ..

echo ""
echo "=========================================="
echo "  Frontend     : http://localhost:5173"
echo "  Backend      : http://localhost:5000"
echo "  MCP SSE      : http://localhost:5001/mcp/sse"
echo "  MiniMax MCP  : http://localhost:5002/mcp/sse"
echo "=========================================="
echo "Press Ctrl+C to stop all services."
echo ""

# === Trap and Wait ===
trap "echo '[exit] Shutting down...'; kill $BACKEND_PID $MCP_PID $MINIMAX_MCP_PID $FRONTEND_PID 2>/dev/null" INT TERM
wait $BACKEND_PID $MCP_PID $MINIMAX_MCP_PID $FRONTEND_PID

