#!/bin/bash
source venv/bin/activate

# ✅ 启动 waitress，监听所有地址（适合 Nginx 代理）
waitress-serve --host=0.0.0.0 --port=5000 app:app