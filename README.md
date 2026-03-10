# AI Finance

AI Finance 是一个支持自然语言记账的个人财务助手，提供 Web 前端、REST 后端与 **MCP 接口**三种使用方式。

- **Web 界面**：对话式记账 + 账本管理 + 图表统计
- **MCP Server**：让任意支持 MCP 协议的 AI Agent 直接调用记账工具，无需登录

## 功能特性

- 自然语言记账（支出 / 收入）
- 分类管理与月度预算设置
- 消费统计与图表可视化
- LLM 配置（支持任意兼容 OpenAI 格式的接口，如 SiliconFlow、DeepSeek 等）
- MCP Server（SSE 传输，Bearer 鉴权，供 AI Agent 直接调用）
- 管理员用户管理

## 项目结构

```
backend/          # Flask 后端 + SQLite 数据库
  app.py          # REST API
  mcp_server.py   # MCP Server（FastMCP + uvicorn）
  .env.example    # 环境变量示例
frontend/         # Vue 3 + Element Plus 前端
skills/
  ai-finance.md   # Agent Skill 文件（见下方说明）
deploy.sh         # 一键启动脚本（Linux / macOS）
deploy.ps1        # 一键启动脚本（Windows）
```

## 快速开始

### 环境要求

- Python >= 3.10
- Node.js >= 18

### 1. 配置环境变量

```bash
cp backend/.env.example backend/.env
```

编辑 `backend/.env`，填入以下内容：

| 变量 | 说明 |
|---|---|
| `DEEPSEEK_API_KEY` | LLM API Key（SiliconFlow / DeepSeek 等） |
| `SECRET_KEY` | Flask Session 密钥，随机字符串即可 |
| `MCP_PORT` | MCP 监听端口（默认 `5001`） |

> **无需配置独立 API Key**：MCP Server 直接使用 Web 账号的用户名和密码进行鉴权，注册好账号即可接入。

### 2. 启动服务

#### Linux / macOS

```bash
chmod +x deploy.sh
./deploy.sh
```

#### Windows（PowerShell）

```powershell
Set-ExecutionPolicy -Scope Process Bypass
./deploy.ps1
```

启动成功后将看到：

```
==========================================
  Frontend : http://localhost:5173
  Backend  : http://localhost:5000
  MCP SSE  : http://localhost:5001/mcp/sse
==========================================
```

按 `Ctrl+C` 停止所有服务。

### 3. 登录前端

浏览器访问 [http://localhost:5173](http://localhost:5173)，默认管理员账号：

```
用户名: admin
密码:   admin
```

---

## MCP 接入

MCP Server 使用 **SSE 传输**，兼容所有支持 MCP 协议的客户端。

- **SSE 端点**：`http://localhost:5001/mcp/sse`
- **鉴权方式**：HTTP Header `Authorization: Bearer <MCP_API_KEY>`

### Claude Code

在 `~/.claude.json` 的 `mcpServers` 中添加：

```json
{
  "mcpServers": {
    "ai-finance": {
      "type": "sse",
      "url": "http://localhost:5001/mcp/sse",
      "headers": {
        "Authorization": "Bearer your_username:your_password"
      }
    }
  }
}
```

将 `your_username:your_password` 替换为你在 Web 前端注册的账号和密码，重启 Claude Code 后即可使用。每个用户填入自己的凭据，数据天然隔离。

### 其他 MCP 客户端

任何支持 SSE 传输的 MCP 客户端均可按相同方式配置，`Authorization` Header 格式固定为 `Bearer username:password`。

### Agent Skill

`skills/` 目录包含两个文件，覆盖不同类型的 Agent 接入场景：

| 文件 | 用途 |
|---|---|
| `ai-finance.md` | Skill 描述文件，供 Agent 理解可用工具及调用规范 |
| `finance_client.py` | MCP 客户端脚本，供不支持 MCP 协议的 Agent 通过命令行或 Python import 调用 |

**Claude Code 用法**：将 `ai-finance.md` 复制到 `~/.claude/skills/ai-finance.md`，在对话中执行 `/ai-finance` 即可激活。

**非 MCP Agent**：激活 `backend/venv`，设置 `FINANCE_USERNAME` 和 `FINANCE_PASSWORD` 环境变量后，直接调用 `finance_client.py`：
```bash
python finance_client.py add_record --category 餐饮 --amount 25.0
python finance_client.py query_records --month 2026-03
```
或在 Python 代码中 `from finance_client import add_record, query_records` 直接调用。

详细参数说明与示例见 `skills/ai-finance.md`。

---

## MCP 工具列表

| 工具 | 说明 |
|---|---|
| `add_record` | 记录一笔支出 |
| `add_income` | 记录一笔收入 |
| `query_records` | 查询支出明细（支持按分类、月份、日期范围筛选） |
| `query_income` | 查询收入记录 |
| `category_sum` | 统计支出总额 |
| `budget_remain` | 查询预算剩余 |
| `set_budget` | 设置或更新月预算 |
| `analyze_spend` | 生成月度消费/收入排行分析 |
| `list_categories` | 获取所有分类列表 |

详细参数说明见 `skills/ai-finance.md`。

---

## 管理员功能

管理员登录后可在侧边菜单访问「用户管理」页面，也可直接调用以下接口：

- `GET /api/users`：查看所有普通用户
- `PUT /api/users/<id>/password`：修改指定用户密码
- `POST /api/users/batch_delete`：批量删除用户（参数 `user_ids` 为 ID 数组）

---

## License

MIT
