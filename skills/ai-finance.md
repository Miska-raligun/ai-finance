You are helping the user manage their personal finances using the AI Finance MCP server.

Choose one of the two integration methods below based on your environment.

---

## Method A: MCP-native clients (Claude Code, etc.)

If your agent runtime supports the MCP protocol natively (e.g. Claude Code with `mcpServers` configured), call the tools directly.

### Available tools

**`add_record`** — Record an expense.
- `category` (str, required): expense category
- `amount` (float, required): amount in CNY
- `note` (str, optional): memo
- `date` (str, optional): YYYY-MM-DD, defaults to today

**`add_income`** — Record an income entry.
- `category` (str, required): income source
- `amount` (float, required): amount in CNY
- `note` (str, optional): memo
- `date` (str, optional): YYYY-MM-DD, defaults to today

**`query_records`** — Query expense records.
- `category` (str, optional): filter by category
- `month` (str, optional): filter by month YYYY-MM
- `start_date` (str, optional): YYYY-MM-DD
- `end_date` (str, optional): YYYY-MM-DD
- `limit` (int, optional): max results, default 20

**`query_income`** — Query income records.
- `source` (str, optional): filter by source
- `month` (str, optional): filter by month YYYY-MM
- `show_all` (bool, optional): return full list with total

**`category_sum`** — Sum total expenses.
- `category` (str, optional): filter by category
- `month` (str, optional): filter by month YYYY-MM
- `start_date` (str, optional): YYYY-MM-DD
- `end_date` (str, optional): YYYY-MM-DD

**`budget_remain`** — Check budget remaining.
- `month` (str, optional): YYYY-MM, defaults to current month
- `category` (str, optional): specific category; omit to return all

**`set_budget`** — Set or update a monthly budget.
- `category` (str, required): expense category
- `amount` (float, required): budget amount
- `month` (str, optional): YYYY-MM, defaults to current month

**`analyze_spend`** — Monthly spending/income breakdown report.
- `month` (str, optional): YYYY-MM, defaults to current month

**`list_categories`** — List all categories. No parameters.

---

## Method B: Non-MCP agents (subprocess or Python import)

Use `skills/finance_client.py` from the repository. It requires the same Python environment as the backend (`backend/venv`).

### Prerequisites

```bash
# activate the backend venv
source /path/to/ai-finance/backend/venv/bin/activate

# set env vars (or export them in your agent's environment)
export FINANCE_MCP_URL=http://localhost:5001/mcp/sse
export MCP_API_KEY=your_mcp_api_key_here
```

### CLI usage (subprocess)

```bash
# Record an expense
python finance_client.py add_record --category 餐饮 --amount 25.0 --note 麦当劳 --date 2026-03-10

# Record income
python finance_client.py add_income --category 工资 --amount 8000.0 --date 2026-03-10

# Query recent expense records
python finance_client.py query_records --month 2026-03 --limit 10

# Query expense records by date range
python finance_client.py query_records --start_date 2026-03-01 --end_date 2026-03-10

# Query income records
python finance_client.py query_income --month 2026-03
python finance_client.py query_income --show_all

# Sum expenses
python finance_client.py category_sum --month 2026-03
python finance_client.py category_sum --category 餐饮 --start_date 2026-03-01 --end_date 2026-03-31

# Check budget remaining (all categories this month)
python finance_client.py budget_remain
python finance_client.py budget_remain --category 餐饮 --month 2026-03

# Set a budget
python finance_client.py set_budget --category 餐饮 --amount 1000.0 --month 2026-03

# Monthly analysis report
python finance_client.py analyze_spend --month 2026-03

# List all categories
python finance_client.py list_categories
```

### Python import usage

```python
from finance_client import (
    add_record, add_income,
    query_records, query_income,
    category_sum, budget_remain,
    set_budget, analyze_spend,
    list_categories,
    call_tool,   # generic: call_tool("tool_name", {"param": "value"})
)

# Record an expense
print(add_record("餐饮", 25.0, note="麦当劳"))

# Record income
print(add_income("工资", 8000.0, date="2026-03-10"))

# Query records
print(query_records(month="2026-03", limit=10))

# Sum expenses for a date range
print(category_sum(start_date="2026-03-01", end_date="2026-03-10"))

# Check budget
print(budget_remain())

# Set budget
print(set_budget("餐饮", 1000.0))

# Monthly analysis
print(analyze_spend("2026-03"))

# List categories
print(list_categories())
```

---

## Usage notes

- All monetary values are in CNY (¥).
- Resolve relative dates ("yesterday", "last week") to concrete YYYY-MM-DD values before calling tools.
- When recording multiple items, call the tool once per item.
- The frontend dashboard at `http://localhost:5173` shows all data visually.
