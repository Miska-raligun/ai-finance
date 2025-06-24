#!/bin/bash
echo "[backend] Activating virtual environment..."
source venv/bin/activate

echo "[backend] Installing Python dependencies..."
pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 100
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 100

export FLASK_APP=app.py
export FLASK_ENV=development
flask run --host=0.0.0.0 --port=5000