from flask import Flask
from flask_cors import CORS
from db import init_db, init_app
from dotenv import load_dotenv
import os, secrets, logging
from datetime import timedelta
from llm_security_middleware import register_llm_security

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]
)

init_db()
load_dotenv()

app = Flask(__name__)
register_llm_security(app)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(16))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
CORS(app, supports_credentials=True)
init_app(app)

# 注册 Blueprints
from routes.auth import auth_bp
from routes.chat import chat_bp
from routes.records import records_bp
from routes.income import income_bp
from routes.categories import categories_bp
from routes.budgets import budgets_bp
from routes.stats import stats_bp
from routes.admin import admin_bp

for bp in [auth_bp, chat_bp, records_bp, income_bp,
           categories_bp, budgets_bp, stats_bp, admin_bp]:
    app.register_blueprint(bp)

if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=5000)
