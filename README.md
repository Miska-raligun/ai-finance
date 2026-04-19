# AI Finance

AI Finance 是一个支持自然语言记账的个人财务助手，提供 Web 前端、REST 后端与 **MCP 接口**三种使用方式。

- **Web 界面**：对话式记账 + 账本管理 + 图表统计
- **MCP Server**：让任意支持 MCP 协议的 AI Agent 直接调用记账工具，无需登录

## 功能特性

### 智能记账
- 自然语言记账（支出 / 收入），聊天或语音即可录入
- 图片识别：上传账单 / 小票 / 发票截图自动提取金额、分类
- 异常支出检测：偏离历史习惯的单笔消费会自动打上标记
- 分类管理与月度预算设置，超支实时预警
- 消费统计与图表可视化，支持月度趋势与分类排行
- 服务端全局排序的账本表，大数据量下依然流畅

### AI 月度报告
- 一键生成当月 Markdown 报告（含 KPI 卡 + 分类表 + 异常提醒 + 建议）
- 报告持久化到 `reports` 表，可回查历史；支持导出 CSV / PDF

### 投资理财
- 资产、持仓、理财目标多维管理，目标进度实时可视化
- 股票 / 基金行情自动同步：输入代码即可，系统按 `持仓 × 最新价` 自动算市值与盈亏（新浪财经 / 天天基金源，10 分钟 TTL 缓存）
- 风险测评问卷 → 对应目标配比 → 再平衡建议，悬停 ℹ️ 查看算法说明
- 聊天 / 图片联动：截图持仓或对 Anon 说「我买了 100 股贵州茅台」，AI 识别后弹出**可编辑待确认卡片**，确认即入库（和记账体验一致）
- 理财目标三色优先级徽章（高 红 / 中 橙 / 低 灰），影响 AI 方案推荐档位（激进 / 平衡 / 保守）
- AI 投资顾问：一键诊断持仓、自定义问答、生成储蓄方案

### 系统
- LLM 配置（支持任意兼容 OpenAI 格式的接口，如 SiliconFlow、DeepSeek 等）
- MCP Server（SSE 传输，Bearer 鉴权，供 AI Agent 直接调用）
- 速率限制、图片大小校验、请求追踪 ID 等基础安全
- 管理员用户管理

## 项目结构

```
backend/
  app.py            # REST API 主入口
  mcp_server.py     # MCP Server（FastMCP + uvicorn）
  handlers.py       # LLM 工具调用落地函数（记账 / 投资 / 预算 / 报告）
  tools.py          # FINANCE_TOOLS schema（LLM tool-calling）
  routes/           # chat / investment / reports / export / admin 等蓝图
  services/
    quotes.py       # 股票 / 基金行情抓取 + 缓存
    portfolio.py    # 持仓诊断、再平衡、目标方案
    reports.py      # 月度报告聚合 + LLM 撰写
    anomaly.py      # 异常消费检测
  migrations/       # 按文件名顺序执行的 SQL 迁移
  prompts/          # 各场景 LLM prompt 模板
  .env.example
frontend/
  src/views/        # ChatView / LedgerView / InvestmentView / ReportsView / AdminView
  src/components/   # RecordTable / AssetTable / GoalProgress / PendingAssetCard 等
  src/stores/       # Pinia stores（user / categories / investment / reports / chat）
skills/ai-finance.md  # Agent Skill 文件（见下方说明）
deploy.sh / deploy.ps1  # 一键启动脚本
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

## 远程 MCP 接入

MCP Server 使用 **SSE 传输**，供运行在**其他设备**上的 AI Agent 远程调用记账功能。Agent 无需关心服务器内部实现，只需知道三样东西：**服务器 IP**、**用户名**、**密码**。

- **SSE 端点**：`http://<服务器IP>:5001/mcp/sse`
- **鉴权方式**：HTTP Header `Authorization: Bearer <用户名>:<密码>`（即 Web 前端的注册账号）

> 确保服务器防火墙已放行 **5001** 端口。

### Claude Code（远程 Agent）

在**你自己电脑**的 `~/.claude.json` 中添加 MCP Server 配置：

```json
{
  "mcpServers": {
    "ai-finance": {
      "type": "sse",
      "url": "http://<服务器IP>:5001/mcp/sse",
      "headers": {
        "Authorization": "Bearer 你的用户名:你的密码"
      }
    }
  }
}
```

重启 Claude Code 后即可直接调用记账工具。每个用户填入自己的凭据，数据天然隔离。

### 其他 MCP 客户端

任何支持 SSE 传输的 MCP 客户端均可按相同方式配置，`Authorization` Header 格式固定为 `Bearer 用户名:密码`。

### Agent Skill（Claude Code）

将 `skills/ai-finance.md` 复制到你自己电脑的 `~/.claude/skills/ai-finance.md`，在对话中执行 `/ai-finance` 即可让 Agent 了解所有可用工具及调用规范。

详细工具参数说明见 `skills/ai-finance.md`。

---

## MCP 工具列表

### 记账
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

### 投资理财
| 工具 | 说明 |
|---|---|
| `add_asset` | 新增资产（同一用户下名称唯一，重复会拒绝） |
| `update_asset_value` | 按名称更新资产当前市值（手动场景） |
| `update_asset` | 按 ID 更新资产任意字段（名称 / 代码 / 持仓 / 成本 / 备注） |
| `delete_asset` | 按 ID 删除资产（连带交易流水） |
| `add_goal` | 新增理财目标（支持 priority 1~5） |
| `portfolio_summary` | 查看持仓总览、分布、盈亏 Top3 |
| `refresh_portfolio_prices` | 强制刷新股票/基金行情（忽略 10 分钟缓存） |
| `quote_symbol` | 按代码查询最新行情（不持久化，纯查询） |

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
