<template>
  <el-card v-if="report" class="report-card">
    <template #header>
      <div class="header-row">
        <span class="title">📑 {{ report.period }} 月度报告</span>
        <span class="ts">生成于 {{ formatTime(report.created_at) }}</span>
      </div>
    </template>

    <div v-if="report.insights" class="kpis">
      <div class="kpi">
        <div class="kpi-label">总支出</div>
        <div class="kpi-value spend">¥{{ fmt(report.insights.spend_total) }}</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">总收入</div>
        <div class="kpi-value income">¥{{ fmt(report.insights.income_total) }}</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">净结余</div>
        <div class="kpi-value" :class="report.insights.net >= 0 ? 'income' : 'spend'">
          ¥{{ fmt(report.insights.net) }}
        </div>
      </div>
      <div v-if="report.insights.anomalies?.length" class="kpi">
        <div class="kpi-label">异常笔数</div>
        <div class="kpi-value warn">{{ report.insights.anomalies.length }}</div>
      </div>
    </div>

    <div class="markdown" v-html="rendered"></div>
  </el-card>

  <el-empty v-else description="暂无报告，请先生成" />
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  report: { type: Object, default: null },
})

function fmt(n) {
  if (n == null) return '0.00'
  return Number(n).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatTime(iso) {
  if (!iso) return ''
  return iso.replace('T', ' ').slice(0, 16)
}

// 简易 Markdown 渲染（标题/列表/强调/表格/换行）
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
const inline = (s) => esc(s)
  .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  .replace(/`([^`]+)`/g, '<code>$1</code>')

const isTableRow = (line) => /^\s*\|.*\|\s*$/.test(line)
const isTableSep = (line) => /^\s*\|?[\s\-:|]+\|?\s*$/.test(line) && line.includes('-')
const isHorizRule = (line) => /^\s*(?:[-*_]\s*){3,}\s*$/.test(line) && !isTableRow(line)
const splitRow = (line) => line.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim())

function renderMarkdown(md) {
  if (!md) return ''
  const lines = md.split('\n')
  const out = []
  let i = 0
  let inList = false
  const closeList = () => { if (inList) { out.push('</ul>'); inList = false } }

  while (i < lines.length) {
    const line = lines[i]

    // 表格：表头 + 分隔行 + 若干数据行
    if (isTableRow(line) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      closeList()
      const header = splitRow(line)
      i += 2
      const body = []
      while (i < lines.length && isTableRow(lines[i]) && !isTableSep(lines[i])) {
        body.push(splitRow(lines[i]))
        i++
      }
      const ths = header.map(c => `<th>${inline(c)}</th>`).join('')
      const trs = body.map(r => '<tr>' + r.map(c => `<td>${inline(c)}</td>`).join('') + '</tr>').join('')
      out.push(
        `<div class="md-table-wrap"><table class="md-table">` +
        `<thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table></div>`
      )
      continue
    }

    // 水平分隔线（--- / *** / ___ / - - -）
    if (isHorizRule(line)) { closeList(); out.push('<hr class="md-hr" />'); i++; continue }

    // 标题
    let m
    if ((m = line.match(/^###\s+(.+)$/))) { closeList(); out.push(`<h3>${inline(m[1])}</h3>`); i++; continue }
    if ((m = line.match(/^##\s+(.+)$/)))  { closeList(); out.push(`<h2>${inline(m[1])}</h2>`); i++; continue }
    if ((m = line.match(/^#\s+(.+)$/)))   { closeList(); out.push(`<h1>${inline(m[1])}</h1>`); i++; continue }

    // 列表
    if ((m = line.match(/^\s*[-*]\s+(.+)$/))) {
      if (!inList) { out.push('<ul>'); inList = true }
      out.push(`<li>${inline(m[1])}</li>`)
      i++
      continue
    }

    closeList()

    // 空行
    if (/^\s*$/.test(line)) { i++; continue }

    // 段落
    out.push(`<p>${inline(line)}</p>`)
    i++
  }
  closeList()
  return out.join('\n')
}

const rendered = computed(() => renderMarkdown(props.report?.content || ''))
</script>

<style scoped>
.report-card { border-radius: 12px; }
.header-row {
  display: flex; justify-content: space-between; align-items: center; gap: 12px;
}
.title { font-weight: 600; font-size: 16px; }
.ts { color: var(--color-text-muted); font-size: 12px; }
.kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.kpi {
  background: var(--color-bg-soft, #F8FAFC);
  border-radius: 10px;
  padding: 12px 14px;
  border: 1px solid var(--color-border, #E5E7EB);
}
.kpi-label { font-size: 12px; color: var(--color-text-muted); margin-bottom: 4px; }
.kpi-value { font-size: 20px; font-weight: 600; }
.kpi-value.spend { color: #DC2626; }
.kpi-value.income { color: #16A34A; }
.kpi-value.warn { color: #D97706; }
.markdown :deep(h1) { font-size: 20px; margin: 12px 0 6px; }
.markdown :deep(h2) { font-size: 17px; margin: 14px 0 6px; color: var(--color-primary, #3B82F6); }
.markdown :deep(h3) { font-size: 15px; margin: 10px 0 4px; }
.markdown :deep(p)  { margin: 6px 0; line-height: 1.7; }
.markdown :deep(ul) { padding-left: 20px; margin: 6px 0; }
.markdown :deep(li) { line-height: 1.7; }
.markdown :deep(code) { background: #F1F5F9; padding: 1px 6px; border-radius: 4px; font-size: 12px; }
.markdown :deep(.md-table-wrap) {
  /* 窄屏时表格太宽自动允许横向滚动，不再被卡片裁掉 */
  max-width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  margin: 10px 0;
  border-radius: 6px;
}
.markdown :deep(.md-table) {
  border-collapse: collapse;
  min-width: 100%;       /* 宽屏撑满卡片 */
  width: max-content;    /* 窄屏按内容展开，由外层 wrap 提供滚动 */
  font-size: 13px;
}
.markdown :deep(.md-table th),
.markdown :deep(.md-table td) {
  border: 1px solid var(--color-border, #E5E7EB);
  padding: 6px 10px;
  text-align: left;
  white-space: nowrap;   /* 避免数字/百分比被折行挤出单元格 */
}
.markdown :deep(.md-table th) { background: #F8FAFC; }

/* 手机端进一步收窄字号和内边距，给表格留更多横向空间 */
@media (max-width: 768px) {
  .markdown :deep(.md-table) { font-size: 12px; }
  .markdown :deep(.md-table th),
  .markdown :deep(.md-table td) { padding: 5px 8px; }
}
.markdown :deep(.md-hr) {
  border: none;
  border-top: 1px solid var(--color-border, #E5E7EB);
  margin: 14px 0;
}
</style>
