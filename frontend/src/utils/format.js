/**
 * 公共格式化工具：金额 / 日期 / 百分比 / 涨跌颜色。
 *
 * 抽这层是为了把散落在 RecapCard / FinancialCheckup / MonthlyReport / ChartPanel /
 * AssetTable 等处的 toFixed(2) + toLocaleString + 正负色判断收敛到一处，
 * 改千分位 / 货币符号 / 配色只动一个文件。
 */

/** 金额格式化为 "1,234,567.00"（无符号）；输入 null/undefined 返回 "0.00"。 */
export function fmtMoney(n, { digits = 2 } = {}) {
  if (n == null || isNaN(n)) return digits > 0 ? '0.' + '0'.repeat(digits) : '0'
  return Number(n).toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

/** 金额带 ¥ 前缀；负数显示成 "-¥1.00"（不放在数字里）。 */
export function fmtCNY(n, opts) {
  const v = Number(n) || 0
  return `${v < 0 ? '-' : ''}¥${fmtMoney(Math.abs(v), opts)}`
}

/**
 * ISO 时间 → 人类可读。kind:
 *   'date'    -> 'YYYY-MM-DD'
 *   'minute'  -> 'YYYY-MM-DD HH:MM'
 *   'second'  -> 'YYYY-MM-DD HH:MM:SS'
 *   'mmdd'    -> 'MM-DD'
 */
export function fmtDate(iso, kind = 'minute') {
  if (!iso) return ''
  const s = String(iso).replace('T', ' ')
  if (kind === 'date') return s.slice(0, 10)
  if (kind === 'minute') return s.slice(0, 16)
  if (kind === 'second') return s.slice(0, 19)
  if (kind === 'mmdd') return s.slice(5, 10)
  return s
}

/** 百分比，默认保留 1 位。带或不带符号 by opt.sign。 */
export function fmtPct(n, { digits = 1, sign = false } = {}) {
  if (n == null || isNaN(n)) return '—'
  const v = Number(n)
  const s = v.toFixed(digits)
  return sign && v > 0 ? `+${s}%` : `${s}%`
}

/**
 * 收支语义配色：正数（收入 / 盈利）= 绿，负数（支出 / 亏损）= 红。
 * 返回 CSS 类名 ('income' | 'spend' | '')，与现有 `.income/.spend` 主题色对齐。
 * 注意：app 里「股票涨/盈」是红（中式），但这个函数是为「收支结余 / 净流入」准备的西式语义。
 */
export function signColor(n) {
  if (n == null || isNaN(n)) return ''
  const v = Number(n)
  if (v > 0) return 'income'
  if (v < 0) return 'spend'
  return ''
}
