"""
MiniMax Coding Plan MCP Server (SSE 模式)
用途：为 Flask 后端提供 understand_image 图片识别能力
运行：python minimax_mcp_server.py
端口：MINIMAX_MCP_PORT（默认 5002）
"""
import os
import sys
import logging

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

api_key = os.getenv("MINIMAX_API_KEY", "")
api_host = os.getenv("MINIMAX_API_HOST", "https://api.minimaxi.com")
port = int(os.getenv("MINIMAX_MCP_PORT", "5002"))

if not api_key:
    logger.error("MINIMAX_API_KEY 未设置，请在 .env 中配置")
    sys.exit(1)

# 设置 minimax-coding-plan-mcp 所需的环境变量
os.environ["MINIMAX_API_KEY"] = api_key
os.environ["MINIMAX_API_HOST"] = api_host

from minimax_mcp.server import mcp  # noqa: E402

if __name__ == "__main__":
    import uvicorn

    app = mcp.http_app(path="/mcp")
    logger.info("MiniMax MCP Server 启动，端口 %d，API Host: %s", port, api_host)
    uvicorn.run(app, host="0.0.0.0", port=port)
