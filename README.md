# AI Finance

AI Finance 是一个支持自然语言记账的个人财务助手，提供 Web 前端、REST 后端与 **MCP 接口**三种使用方式。

- **Web 界面**：对话式记账 + 账本管理 + 图表统计
- **MCP Server**：让任意支持 MCP 协议的 AI Agent 直接调用记账工具，无需登录

## 功能特性

### 智能记账
- 自然语言记账（支出 / 收入），聊天或语音即可录入
- 图片识别：上传账单 / 小票 / 发票截图自动提取金额、分类
- **定期账单**：水电、订阅、房租等周期性扣款建一次规则，cron 每天展开当日到期的笔目
- **收据归档**：上传发票/小票图片，自动绑定到记录上备查
- 异常支出检测：偏离历史习惯的单笔消费会自动打上标记
- 分类管理与月度预算设置，超支实时预警
- **热力日历 + 桑基图**：年度支出热力图直观看到「哪天最败家」；收入桑基图按"来源 → 分类 → 净结余"可视化资金流
- 服务端全局排序的账本表，大数据量下依然流畅
- 软删除：误删记录可在管理端恢复

### AI 助手 Anon
- **💭 买之前问一下（决策助手）**：输入"想买什么 + 价格 + 分类"，结合你近 3 月真实支出、本月预算余量、储蓄目标进度，Anon 给出"建议买 / 等等 / 更便宜替代 / 放弃"的个性化判断
- **🩺 财务体检**：基于真实数据由 AI 打 0-100 健康分，分储蓄率 / 预算执行 / 投资情况 / 消费结构四维拆解 + 趋势折线
- **✨ 本月回顾卡片**：动森风可视化卡，AI 写俏皮回顾文案，一键导出 PNG 分享
- **AI 月度报告**：一键生成 Markdown 报告（KPI 卡 + 分类表 + 异常提醒 + 建议），LLM 长任务异步生成 + 状态轮询，持久化到 `reports` 表可回查 / 导出 CSV / PDF
- 配置个性化 Persona，让 Anon 用你喜欢的语气说话；所有 AI 路径在无 key / 解析失败时都有本地规则兜底

### 投资理财
- 资产、持仓、理财目标多维管理，目标进度实时可视化（攒钱目标用**动森风小岛进度条**，100% 庆祝特效）
- 股票 / 基金行情自动同步：输入代码即可，系统按 `持仓 × 最新价` 自动算市值与盈亏（新浪财经 / 天天基金源，10 分钟 TTL 缓存）
- **资产市值历史快照**：每次刷新行情写一条快照，AssetTable 抽屉里画历史折线（保留 90 天，定期清理）
- 风险测评问卷 → 对应目标配比 → 再平衡建议，悬停 ℹ️ 查看算法说明
- 聊天 / 图片联动：截图持仓或对 Anon 说「我买了 100 股贵州茅台」，AI 识别后弹出**可编辑待确认卡片**，确认即入库（和记账体验一致）
- 理财目标三色优先级徽章（高 红 / 中 橙 / 低 灰），影响 AI 方案推荐档位（激进 / 平衡 / 保守）
- AI 投资顾问：一键诊断持仓、自定义问答、生成储蓄方案

### 系统与界面
- **多 LLM 厂商**：原生支持 OpenAI 兼容（DeepSeek / SiliconFlow / Qwen / Kimi / 智谱 / Ollama）、Anthropic Claude、Google Gemini 三家，UI 配置弹窗里一键切换（详见下文「LLM 厂商配置」）
- **🎨 主题系统**：默认动森暖色 + 四季 / 暗色等多套配色，可手动切或按月自动跟季节
- **动森风视觉**：原创小动物头像（兔/柴犬/猫头鹰/河狸/狐狸）、波浪/椰子树等装饰素材，配有机圆角、3D 阴影
- LLM API Key 加密存储（Fernet）、CSRF 双重提交保护、LLM-WAF 频率限制 + 安全模式、CSP / HSTS / X-Frame-Options 等响应头加固
- **每日 token 配额**：可在 `.env` 设 `LLM_DAILY_TOKEN_LIMIT` 限制单用户每日 LLM 用量，并发预占用 SQLite IMMEDIATE 事务防越线
- 管理端 `llm_usage` 看板：各端点延迟 P95 / 失败率 / token 消耗一目了然
- MCP Server（SSE 传输，Bearer 鉴权，供 AI Agent 直接调用）
- 速率限制、图片大小校验、请求追踪 ID 等基础安全
- 管理员用户管理 + 自助账号注销（GDPR 删除）

## 项目结构

```
backend/
  app.py             # REST API 主入口（注册 CSRF / WAF / 限流 / 蓝图）
  mcp_server.py      # MCP Server（FastMCP + uvicorn）
  csrf.py            # CSRF 双重提交防护
  crypto.py          # LLM apikey 加密 / 解密（Fernet）
  llm_security_middleware.py  # LLM-WAF：白名单 + 频率限制
  handlers/          # LLM 工具调用落地（records / income / budgets / categories / analysis / investment）
  routes/            # chat / decide / checkup / reports / stats / investment / recurring / receipts / health / admin ...
  services/
    llm.py           # 统一 LLM 调用入口 + 配额预占
    llm_providers/   # openai_compat / anthropic / gemini 三家协议适配
    llm_config.py    # llm_config 表读写 + persona 过滤
    quotes.py        # 股票 / 基金行情抓取 + 缓存
    portfolio.py     # 持仓诊断、再平衡、目标方案
    reports.py       # 月度报告异步生成 + 孤儿任务清理
    recap.py         # 本月回顾卡亮点 + AI 文案
    checkup.py       # 财务体检评分（LLM + 本地规则兜底）
    recurring.py     # 定期账单展开
    asset_history.py # 资产市值快照
    anomaly.py       # 异常消费检测
  migrations/        # 按文件名顺序执行的 SQL 迁移（已到 0014）
  prompts/           # 各场景 LLM prompt 模板
  .env.example
frontend/
  src/views/         # Home / Chat / Ledger / Investment / Reports / Admin / Login
  src/components/    # DecisionHelper / FinancialCheckup / RecapCard / MonthlyReport / IslandProgress /
                     # SpendCalendar / IncomeSankey / RecurringRules / ThemePicker / RecordTable / AssetTable ...
  src/stores/        # Pinia stores（user / chat / reports / investment / checkup）
  src/styles/        # animal-theme / themes（四季 + 暗色）
  src/assets/decor/  # 动森风装饰素材（动物头像 / 波浪 / 椰子树 / 纹理）
  src/echarts-theme.js  # ECharts 'animal' 主题
scripts/
  backup_db.sh       # SQLite 备份（deploy.sh 启动前自动调）
  run_recurring.py   # 定期账单 + 资产历史清理 cron（加锁防重叠）
skills/ai-finance.md # Agent Skill 文件
deploy.sh / deploy.ps1  # 一键启动脚本（含启动后 /api/heartbeat 健康检查）
```

## 快速开始

### 环境要求

- Python >= 3.10
- Node.js >= 18

### 1. 配置环境变量

```bash
cp backend/.env.example backend/.env
```

编辑 `backend/.env`，关键变量：

| 变量 | 必填 | 说明 |
|---|---|---|
| `SECRET_KEY` | ✅ | Flask Session 密钥，强烈建议 `openssl rand -hex 32` |
| `DEEPSEEK_API_KEY` |  | 系统默认 LLM 的 key（用户没在 UI 自配时兜底使用） |
| `LLM_SECRET_SALT` |  | 用户级 LLM key 加密派生盐，首次启用后不可修改 |
| `LLM_DAILY_TOKEN_LIMIT` |  | 单用户每日 LLM token 配额，`0` 表示不限 |
| `CSRF_ENABLED` |  | CSRF 校验开关，生产保持 `1` |
| `ALLOWED_ORIGINS` |  | 允许携带 cookie 的跨域来源，逗号分隔 |
| `SESSION_COOKIE_SECURE` |  | 反代上 HTTPS 时设 `1` |
| `REPORT_WORKERS` |  | 月度报告异步生成 worker 数，默认 `2` |
| `MCP_PORT` |  | MCP 监听端口（默认 `5001`） |
| `MINIMAX_API_KEY` |  | 图片识别走 MiniMax MCP 时填 |

> **无需配置独立 API Key**：MCP Server 直接使用 Web 账号的用户名和密码进行鉴权，注册好账号即可接入。

### LLM 厂商配置

后端原生支持三种 provider，登录后在 **⚙ LLM 配置** 弹窗里选 provider + 填 URL/Key/Model：

| Provider | URL 示例 | Model 示例 | 备注 |
|---|---|---|---|
| `openai`（OpenAI 兼容） | `https://api.siliconflow.cn/v1/chat/completions` | `Pro/deepseek-ai/DeepSeek-V3` | 完整 `/chat/completions` 路径；适配 DeepSeek / SiliconFlow / Qwen / Kimi / 智谱 / Ollama 等 |
| `anthropic` | `https://api.anthropic.com` | `claude-sonnet-4-5` | 走 Claude Messages API，URL 写到 host 即可，自动补 `/v1/messages` |
| `gemini` | `https://generativelanguage.googleapis.com` | `gemini-2.5-flash` | API Key 自动注入 query 参数 |

不在 UI 配置时回退到 `.env` 的 `DEEPSEEK_API_KEY` + `DEFAULT_LLM_URL`/`DEFAULT_LLM_MODEL`（见 `backend/constants.py`）。
所有 AI 路径（决策助手 / 体检 / 回顾 / 月报）在无 key / 调用失败时都有本地规则兜底，不会全黑。

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

浏览器访问 [http://localhost:5173](http://localhost:5173)。

**首次启动**会自动创建管理员账号 `admin`，**初始密码随机生成**并写入 `backend/logs/initial_admin.txt`，登录后请尽快改密并删除该文件。

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
