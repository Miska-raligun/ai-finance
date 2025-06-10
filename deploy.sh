#!/bin/bash
set -e

# === Backend Setup ===
pushd backend >/dev/null
if [ ! -d "venv" ]; then
  echo "[backend] Creating virtual environment..."
  python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
export FLASK_APP=app.py
waitress-serve --host=0.0.0.0 --port=5000 app:app &
BACKEND_PID=$!
deactivate
popd >/dev/null

# === Frontend Setup ===
cd frontend
if [ ! -d "node_modules" ]; then
  echo "[frontend] Installing node dependencies..."
  npm install
fi
npm run dev &
FRONTEND_PID=$!
cd ..

trap "kill $BACKEND_PID $FRONTEND_PID" INT TERM
wait $BACKEND_PID $FRONTEND_PID