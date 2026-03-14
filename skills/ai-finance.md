You are helping the user manage their personal finances using the AI Finance server.

Choose one of the two integration methods below based on your environment.

---

## Method A: MCP-native clients (Claude Code, etc.)

If your agent runtime supports the MCP protocol natively, call the tools directly — your MCP client is already connected.

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
- `show_all` (bool, optional): return full list with IDs

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

**`search_records`** — Search expense records by keyword/category/time (use before deleting to get record IDs).
- `分类` (str, optional): filter by category
- `时间范围` (str, optional): YYYY-MM-DD / YYYY-MM / YYYY
- `关键词` (str, optional): keyword matched against note field, e.g. "麦当劳"
- `条数` (int, optional): max results, default 10

**`delete_record`** — Delete an expense record by ID.
- `记录ID` (int, required): ID from `search_records`

**`delete_income`** — Delete an income record by ID.
- `收入ID` (int, required): ID from `query_income`

---

## Method B: Non-MCP agents (subprocess or Python import)

Use `skills/finance_client.py`. It connects to the remote server over HTTP — no server-side setup needed. You only need Python with the `mcp` package installed on **your own machine**.

### Prerequisites

```bash
pip install mcp

# Set these three env vars — server IP, your web account credentials
export FINANCE_MCP_URL=http://<服务器IP>:5001/mcp/sse
export FINANCE_USERNAME=your_username
export FINANCE_PASSWORD=your_password
```

### CLI usage (subprocess)

```bash
# Record an expense
python finance_client.py add_record --category 餐饮 --amount 25.0 --note 麦当劳

# Record income
python finance_client.py add_income --category 工资 --amount 8000.0 --date 2026-03-10

# Query recent expense records
python finance_client.py query_records --month 2026-03 --limit 10

# Query by date range
python finance_client.py query_records --start_date 2026-03-01 --end_date 2026-03-10

# Query income
python finance_client.py query_income --month 2026-03
python finance_client.py query_income --show_all

# Sum expenses
python finance_client.py category_sum --month 2026-03
python finance_client.py category_sum --category 餐饮 --start_date 2026-03-01 --end_date 2026-03-31

# Budget
python finance_client.py budget_remain
python finance_client.py set_budget --category 餐饮 --amount 1000.0

# Monthly analysis
python finance_client.py analyze_spend --month 2026-03

# List categories
python finance_client.py list_categories

# Search records by keyword (get ID before deleting)
python finance_client.py search_records --keyword 麦当劳
python finance_client.py search_records --category 餐饮 --time_range 2026-03

# Delete a record
python finance_client.py delete_record --id 42
python finance_client.py delete_income --id 7
```

### Python import usage

```python
import os
os.environ["FINANCE_MCP_URL"] = "http://<服务器IP>:5001/mcp/sse"
os.environ["FINANCE_USERNAME"] = "your_username"
os.environ["FINANCE_PASSWORD"] = "your_password"

from finance_client import (
    add_record, add_income,
    query_records, query_income,
    category_sum, budget_remain,
    set_budget, analyze_spend,
    list_categories,
    search_records, delete_record, delete_income,
)

print(add_record("餐饮", 25.0, note="麦当劳"))
print(query_records(month="2026-03", limit=10))
print(search_records(keyword="麦当劳"))
print(delete_record(42))
```

---

## Usage notes

- All monetary values are in CNY (¥).
- Resolve relative dates ("yesterday", "last week") to concrete YYYY-MM-DD values before calling tools.
- When recording multiple items, call the tool once per item.
- To delete a record: first call `search_records` with a keyword to get the ID, then call `delete_record`.
