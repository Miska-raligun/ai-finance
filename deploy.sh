#!/bin/bash
set -ex

echo "[start] Deploy script started..."

BACKEND_LOG="backend.log"
FRONTEND_LOG="frontend.log"

# === Backend Setup ===
pushd backend >/dev/null

PORT=5000
PID=$(lsof -ti:$PORT)
if [ -n "$PID" ]; then
  echo "[backend] Port $PORT in use. Killing process $PID..."
  kill -9 $PID
fi

if [ ! -d "venv" ]; then
  echo "[backend] Creating virtual environment..."
  python3 -m venv venv
fi

echo "[backend] Activating virtual environment..."
source venv/bin/activate

echo "[backend] Installing Python dependencies..."
pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 100
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 100

echo "[backend] Starting Waitress on port $PORT..."
waitress-serve --host=0.0.0.0 --port=$PORT app:app > "../$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
echo "[backend] Backend running (PID $BACKEND_PID), logging to $BACKEND_LOG"
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
echo "[frontend] Frontend running (PID $FRONTEND_PID), logging to $FRONTEND_LOG"
cd ..

# === Trap and Wait ===
trap "echo '[exit] Shutting down...'; kill $BACKEND_PID $FRONTEND_PID" INT TERM
wait $BACKEND_PID $FRONTEND_PID

