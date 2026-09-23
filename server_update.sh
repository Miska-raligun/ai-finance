#!/bin/bash
# 服务器侧部署更新脚本
# 用途：拉取最新部署分支代码并重启服务
# 使用前请根据实际情况修改下方服务名称
set -e

# ===== 配置：按实际 systemd 服务名修改 =====
FLASK_SERVICE="jzflask"
MCP_SERVICE="ai-finance-mcp"              # MCP server 服务（端口 5001）
MINIMAX_MCP_SERVICE="ai-finance-minimax-mcp"  # MiniMax MCP 图片识别服务（端口 5002）
DEPLOY_BRANCH="claude/project-optimization-analysis-yq70v"
# ==========================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 1. 备份数据库
DB_FILE="$SCRIPT_DIR/backend/records.db"
if [ -f "$DB_FILE" ]; then
    BACKUP="${DB_FILE}.backup_$(date +%Y%m%d_%H%M%S)"
    cp "$DB_FILE" "$BACKUP"
    echo "[backup] 数据库已备份到 $BACKUP"
else
    echo "[backup] 未找到 $DB_FILE，跳过备份"
fi

# 2. 拉取最新代码（含已构建的 frontend/dist/）
echo "[git] 拉取 $DEPLOY_BRANCH ..."
git fetch origin "$DEPLOY_BRANCH"
git checkout "$DEPLOY_BRANCH"
git pull origin "$DEPLOY_BRANCH"
echo "[git] 代码已更新"

# 3. 安装/更新 Python 依赖
echo "[pip] 检查并安装 requirements.txt 中的依赖..."
"$SCRIPT_DIR/backend/venv/bin/pip" install -r "$SCRIPT_DIR/backend/requirements.txt" \
    -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 100 -q
echo "[pip] 依赖已更新"

# 4. 重启 Flask 服务
echo "[systemd] 重启 $FLASK_SERVICE ..."
systemctl restart "$FLASK_SERVICE"
echo "[systemd] $FLASK_SERVICE 已重启（数据库迁移将在启动时自动执行）"

# 5. 重启 MCP server 服务
echo "[systemd] 重启 $MCP_SERVICE ..."
systemctl restart "$MCP_SERVICE"
echo "[systemd] $MCP_SERVICE 已重启"

# 6. 重启 MiniMax MCP 图片识别服务
if systemctl list-unit-files | grep -q "$MINIMAX_MCP_SERVICE"; then
    echo "[systemd] 重启 $MINIMAX_MCP_SERVICE ..."
    systemctl restart "$MINIMAX_MCP_SERVICE"
    echo "[systemd] $MINIMAX_MCP_SERVICE 已重启"
else
    echo "[warn] $MINIMAX_MCP_SERVICE 服务未创建，跳过。"
    echo "  如需启用图片识别，请创建 systemd 服务："
    echo "    sudo nano /etc/systemd/system/${MINIMAX_MCP_SERVICE}.service"
    echo "  参考 backend/minimax_mcp_server.py 中的说明"
fi

echo ""
echo "=========================================="
echo "  部署完成！"
echo "  请执行以下命令验证："
echo "    systemctl status $FLASK_SERVICE"
echo "    systemctl status $MCP_SERVICE"
echo "    systemctl status $MINIMAX_MCP_SERVICE"
echo "    sqlite3 records.db \".schema records\""
echo "=========================================="
