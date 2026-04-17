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
function renderMarkdown(md) {
  if (!md) return ''
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

  const lines = esc(md).split('\n')
  const out = []
  let inList = false
  let inTable = false
  let tableRows = []

  const flushList = () => {
    if (inList) { out.push('</ul>'); inList = false }
  }
  const flushTable = () => {
    if (inTable) {
      const [head, ...body] = tableRows
      const ths = head.map(c => `<th>${c.trim()}</th>`).join('')
      const trs = body.map(r => '<tr>' + r.map(c => `<td>${c.trim()}</td>`).join('') + '</tr>').join('')
      out.push(`<table class="md-table"><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`)
      inTable = false
      tableRows = []
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const tableMatch = line.match(/^\s*\|(.+)\|\s*$/)
    const sepMatch = line.match(/^\s*\|?[\s\-:|]+\|?\s*$/) && line.includes('-')

    if (tableMatch && !sepMatch) {
      flushList()
      const cells = tableMatch[1].split('|')
      // 跳过分隔行
      if (i + 1 < lines.length && /^\s*\|?[\s\-:|]+\|?\s*$/.test(lines[i + 1]) && lines[i + 1].includes('-')) {
        inTable = true
        tableRows.push(cells)
        continue
      }
      if (inTable) {
        tableRows.push(cells)
        continue
      }
    } else if (inTable && /^\s*$/.test(line)) {
      flushTable()
    } else {
      flushTable()
    }

    if (/^### (.+)$/.test(line)) { flushList(); out.push(`<h3>${RegExp.$1}</h3>`); continue }
    if (/^## (.+)$/.test(line)) { flushList(); out.push(`<h2>${RegExp.$1}</h2>`); continue }
    if (/^# (.+)$/.test(line)) { flushList(); out.push(`<h1>${RegExp.$1}</h1>`); continue }
    if (/^[-*] (.+)$/.test(line)) {
      if (!inList) { out.push('<ul>'); inList = true }
      let item = RegExp.$1
      item = item.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
                 .replace(/`([^`]+)`/g, '<code>$1</code>')
      out.push(`<li>${item}</li>`)
      continue
    }
    flushList()
    if (/^\s*$/.test(line)) { out.push(''); continue }
    let p = line
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
    out.push(`<p>${p}</p>`)
  }
  flushList()
  flushTable()
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
.markdown :deep(.md-table) {
  border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 13px;
}
.markdown :deep(.md-table th),
.markdown :deep(.md-table td) {
  border: 1px solid var(--color-border, #E5E7EB);
  padding: 6px 10px;
  text-align: left;
}
.markdown :deep(.md-table th) { background: #F8FAFC; }
</style>
