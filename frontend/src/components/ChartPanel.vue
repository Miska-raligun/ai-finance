<!-- components/ChartPanel.vue -->
<template>
  <el-card>
    <template #header>📊 收支图表分析</template>

    <div class="toolbar">
      <el-radio-group v-model="mode" size="small">
        <el-radio-button label="month">按月</el-radio-button>
        <el-radio-button label="year">按年</el-radio-button>
      </el-radio-group>
      <el-date-picker
        v-model="selectedTime"
        :type="mode === 'month' ? 'month' : 'year'"
        :value-format="mode === 'month' ? 'YYYY-MM' : 'YYYY'"
        @change="fetchChartData"
        size="small"
        style="width: 140px"
      />
      <el-button size="small" @click="showAll">查看全部</el-button>
    </div>

    <!-- 汇总数字 -->
    <div class="stat-strip">
      <div class="stat-item income">
        <span class="stat-label">收入</span>
        <span class="stat-value">¥{{ fmtNum(totalIncome) }}</span>
        <span v-if="incomeChangePct !== null" :class="['stat-delta', incomeChangePct >= 0 ? 'delta-up' : 'delta-down']">
          {{ incomeChangePct >= 0 ? '↑' : '↓' }} {{ Math.abs(incomeChangePct).toFixed(1) }}%
        </span>
      </div>
      <div class="stat-item expense">
        <span class="stat-label">支出</span>
        <span class="stat-value">¥{{ fmtNum(totalExpense) }}</span>
        <span v-if="expenseChangePct !== null" :class="['stat-delta', expenseChangePct >= 0 ? 'delta-up' : 'delta-down']">
          {{ expenseChangePct >= 0 ? '↑' : '↓' }} {{ Math.abs(expenseChangePct).toFixed(1) }}%
        </span>
      </div>
      <div class="stat-item" :class="totalBalance >= 0 ? 'balance-pos' : 'balance-neg'">
        <span class="stat-label">结余</span>
        <span class="stat-value">{{ totalBalance >= 0 ? '+' : '-' }}¥{{ fmtNum(totalBalance) }}</span>
        <span v-if="balanceChangePct !== null" :class="['stat-delta', balanceChangePct >= 0 ? 'delta-up' : 'delta-down']">
          {{ balanceChangePct >= 0 ? '↑' : '↓' }} {{ Math.abs(balanceChangePct).toFixed(1) }}%
        </span>
      </div>
    </div>

    <div class="chart-row">
      <div class="pie-wrap">
        <el-skeleton v-if="loading" animated>
          <template #template>
            <el-skeleton-item variant="circle" style="width: 200px; height: 200px; margin: 30px auto;" />
          </template>
        </el-skeleton>
        <VChart theme="animal" v-else :option="incomePieOption" style="height: 280px; width: 100%" autoresize />
      </div>
      <div class="pie-wrap">
        <el-skeleton v-if="loading" animated>
          <template #template>
            <el-skeleton-item variant="circle" style="width: 200px; height: 200px; margin: 30px auto;" />
          </template>
        </el-skeleton>
        <VChart theme="animal" v-else :option="spendPieOption" style="height: 280px; width: 100%" autoresize />
      </div>
    </div>

    <el-skeleton v-if="loading" animated :rows="3" style="margin-top: 12px" />
    <VChart theme="animal" v-else :option="lineOption" style="height: 280px; width: 100%" autoresize />
  </el-card>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'

// 读取当前主题的 CSS 变量,让 ECharts(canvas 无法解析 var())也能跟随
// 四季 / 暗色主题。深色主题下标题不再用硬编码的深色而看不见。
function cssVar(name, fallback) {
  // 主题变量覆盖挂在 body[data-theme] 上,必须从 body(或其后代)读,
  // 从 documentElement(html) 读只能拿到 :root 默认值,拿不到暗色/四季覆盖。
  const v = getComputedStyle(document.body).getPropertyValue(name).trim()
  return v || fallback
}
function chartColors() {
  return {
    title: cssVar('--color-text-strong', '#1e293b'),
    axis: cssVar('--color-text-muted', '#64748b'),
    split: cssVar('--color-surface-2', '#eef2f7'),
    line: cssVar('--color-border-light', '#e5e7eb'),
  }
}
import api from '@/api'
import { fmtMoney } from '@/utils/format'
import { use } from 'echarts/core'
import VChart from 'vue-echarts'
import { PieChart, LineChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([PieChart, LineChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent, CanvasRenderer])

const props = defineProps({ refreshFlag: Number })
const mode = ref('month')
const selectedTime = ref()
const loading = ref(true)
const incomePieOption = ref({})
const spendPieOption = ref({})
const lineOption = ref({})
const totalIncome = ref(0)
const totalExpense = ref(0)
const totalBalance = computed(() => totalIncome.value - totalExpense.value)
const incomeChangePct = ref(null)
const expenseChangePct = ref(null)
const balanceChangePct = ref(null)
// 涨/跌幅卡片用：先取绝对值（正负号由相邻箭头 ↑↓ 表达），再走全站统一的金额千分位格式化。
const fmtNum = v => fmtMoney(Math.abs(v))

// Animal Island 主色 + NookPhone 13 色调色板
const PRIMARY = '#19c8b9'
const PALETTE = ['#19c8b9','#f8a6b2','#f7cd67','#82d5bb','#b77dee','#889df0','#e59266','#8ac68a','#fc736d','#d1da49']

function showAll() {
  mode.value = 'year'
  selectedTime.value = ''
  fetchChartData()
}

const fetchChartData = async () => {
  if (!selectedTime.value && mode.value === 'month') return
  loading.value = true
  try {
    await _doFetchChartData()
  } finally {
    loading.value = false
  }
}

const _doFetchChartData = async () => {
  totalIncome.value = 0
  totalExpense.value = 0
  incomeChangePct.value = null
  expenseChangePct.value = null
  balanceChangePct.value = null
  const time = selectedTime.value
  const catParams = {}
  if (mode.value === 'month' && time) catParams.month = time
  else if (mode.value === 'year' && time) catParams.year = time

  const requests = [
    api.get('/api/stats/by-category', { params: catParams }),
    mode.value === 'month'
      ? api.get('/api/stats/daily', { params: { month: time } })
      : (time
          ? api.get('/api/stats/monthly', { params: { year: time } })
          : api.get('/api/stats/yearly'))
  ]
  // 月度环比 / 年度同比对比数据
  if (mode.value === 'month' && time) {
    requests.push(api.get('/api/stats/comparison', { params: { month: time } }))
  } else if (mode.value === 'year' && time) {
    requests.push(api.get('/api/stats/comparison', { params: { year: time } }))
  }
  const results = await Promise.all(requests)
  const [cats, trend] = results
  if (results[2] && results[2].data) {
    const comp = results[2].data
    incomeChangePct.value = comp.income.change_pct
    expenseChangePct.value = comp.expense.change_pct
    balanceChangePct.value = comp.balance.change_pct
  }

  const incomeCats = cats.data.filter(x => x['类型'] === '收入')
  const spendCats = cats.data.filter(x => x['类型'] === '支出')
  totalIncome.value = incomeCats.reduce((s, x) => s + x['金额'], 0)
  totalExpense.value = spendCats.reduce((s, x) => s + x['金额'], 0)
  const fmtCeil = v => (Math.ceil(v * 100) / 100).toFixed(2)

  const pieTooltip = {
    trigger: 'item',
    formatter: p => `${p.name}: ¥${fmtCeil(p.value)} (${p.percent}%)`
  }
  const lineTooltip = {
    trigger: 'axis',
    formatter: params => params.map(p => {
      const sign = p.value < 0 ? '-' : ''
      const absStr = (Math.ceil(Math.abs(p.value) * 100) / 100).toFixed(2)
      return `${p.seriesName}: ${sign}¥${absStr}`
    }).join('<br/>')
  }

  const C = chartColors()
  // 悬停右上角出现下载按钮,一键存 PNG(白底,避免透明背景在相册里看不清)
  const saveTool = (name) => ({
    feature: { saveAsImage: { title: '下载图片', name, backgroundColor: '#ffffff', pixelRatio: 2 } },
    right: 8, top: 2,
  })
  const makePie = (title, data, seriesName) => ({
    color: PALETTE,
    toolbox: saveTool(title),
    title: { text: title, left: 'center', top: 6, textStyle: { fontSize: 13, fontWeight: 600, color: C.title } },
    tooltip: pieTooltip,
    legend: { show: false },
    series: [{
      name: seriesName,
      type: 'pie',
      radius: ['35%', '60%'],
      center: ['50%', '50%'],
      data,
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 13, fontWeight: 'bold' } }
    }]
  })

  incomePieOption.value = makePie('收入分布', incomeCats.map(x => ({ name: x['名称'], value: x['金额'] })), '收入来源')
  spendPieOption.value = makePie('支出分布', spendCats.map(x => ({ name: x['名称'], value: x['金额'] })), '消费分类')

  const lineCommon = {
    color: [PRIMARY, '#fc736d', '#82d5bb'],
    toolbox: saveTool('收支趋势'),
    legend: { data: ['收入', '支出', '结余'], bottom: 0, left: 'center', textStyle: { fontSize: 12 } },
    grid: { top: 36, bottom: 50, left: 50, right: 16 },
    tooltip: lineTooltip,
    xAxis: { type: 'category', axisLine: { lineStyle: { color: C.line } }, axisLabel: { color: C.axis, fontSize: 11 } },
    yAxis: { type: 'value', axisLabel: { color: C.axis, fontSize: 11 }, splitLine: { lineStyle: { color: C.split } } },
  }

  if (mode.value === 'month') {
    lineOption.value = {
      ...lineCommon,
      title: { text: '本月每日收支', left: 'center', top: 4, textStyle: { fontSize: 13, fontWeight: 600, color: '#1e293b' } },
      xAxis: { ...lineCommon.xAxis, data: trend.data.map(d => d.date) },
      series: [
        { name: '收入', type: 'line', smooth: true, data: trend.data.map(d => d['收入']), areaStyle: { opacity: 0.08 } },
        { name: '支出', type: 'line', smooth: true, data: trend.data.map(d => d['支出']), areaStyle: { opacity: 0.08 } },
        { name: '结余', type: 'line', smooth: true, data: trend.data.map(d => d['结余']), areaStyle: { opacity: 0.08 } }
      ]
    }
  } else if (!selectedTime.value) {
    lineOption.value = {
      ...lineCommon,
      title: { text: '历年收支趋势', left: 'center', top: 4, textStyle: { fontSize: 13, fontWeight: 600, color: '#1e293b' } },
      xAxis: { ...lineCommon.xAxis, data: trend.data.map(m => m.year) },
      series: [
        { name: '收入', type: 'line', smooth: true, data: trend.data.map(m => m['收入']), areaStyle: { opacity: 0.08 } },
        { name: '支出', type: 'line', smooth: true, data: trend.data.map(m => m['支出']), areaStyle: { opacity: 0.08 } },
        { name: '结余', type: 'line', smooth: true, data: trend.data.map(m => m['收入'] - m['支出']), areaStyle: { opacity: 0.08 } }
      ]
    }
  } else {
    lineOption.value = {
      ...lineCommon,
      title: { text: '年度收支趋势', left: 'center', top: 4, textStyle: { fontSize: 13, fontWeight: 600, color: '#1e293b' } },
      xAxis: { ...lineCommon.xAxis, data: trend.data.map(m => m.month) },
      series: [
        { name: '收入', type: 'line', smooth: true, data: trend.data.map(m => m['收入']), areaStyle: { opacity: 0.08 } },
        { name: '支出', type: 'line', smooth: true, data: trend.data.map(m => m['支出']), areaStyle: { opacity: 0.08 } },
        { name: '结余', type: 'line', smooth: true, data: trend.data.map(m => m['收入'] - m['支出']), areaStyle: { opacity: 0.08 } }
      ]
    }
  }
}

onMounted(() => {
  selectedTime.value = new Date().toISOString().slice(0, 7)
  fetchChartData()
})
watch(() => props.refreshFlag, fetchChartData)
watch(mode, () => {
  selectedTime.value = mode.value === 'month'
    ? new Date().toISOString().slice(0, 7)
    : new Date().getFullYear().toString()
  fetchChartData()
})

// 切主题(四季 / 暗色)时重算图表配色。ThemePicker 改的是 <html>/<body> 的
// data-theme,监听它变化后重跑一次 build,让标题/坐标轴颜色跟上。
let _themeObserver = null
onMounted(() => {
  _themeObserver = new MutationObserver(() => fetchChartData())
  _themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  _themeObserver.observe(document.body, { attributes: true, attributeFilter: ['data-theme'] })
})
onBeforeUnmount(() => _themeObserver && _themeObserver.disconnect())
</script>

<style scoped>
.stat-strip {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.stat-item {
  flex: 1;
  min-width: 0;
  border-radius: 10px;
  padding: 10px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: var(--color-bg);
}
/* 半透明色调:浅色主题是淡色块,深色主题下自动叠在深底上仍协调 */
.stat-item.income  { background: rgba(34, 197, 94, 0.14); }
.stat-item.expense { background: rgba(244, 63, 94, 0.12); }
.stat-item.balance-pos { background: var(--color-bg); }
.stat-item.balance-neg { background: rgba(249, 115, 22, 0.14); }
.stat-label {
  font-size: 12px;
  color: var(--color-text-muted);
  white-space: nowrap;
}
.stat-value {
  font-size: clamp(13px, 3.2vw, 18px);
  font-weight: 700;
  word-break: break-all;
  line-height: 1.2;
}
.income  .stat-value { color: #16A34A; }
.expense .stat-value { color: #DC2626; }
.balance-pos .stat-value { color: var(--color-primary); }
.balance-neg .stat-value { color: #EA580C; }

.stat-delta {
  font-size: 11px;
  font-weight: 600;
}
.delta-up { color: #22c55e; }
.delta-down { color: #ef4444; }
/* 支出项语义反转：支出减少是好事 */
.stat-item.expense .delta-up { color: #ef4444; }
.stat-item.expense .delta-down { color: #22c55e; }

.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.chart-row {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}
.pie-wrap {
  flex: 1;
  min-width: 0;
  background: var(--color-surface-2, rgba(0, 0, 0, 0.03));
  border-radius: 8px;
  padding: 4px;
}

@media (max-width: 768px) {
  .chart-row { flex-direction: column; }
  .pie-wrap { flex: none; width: 100%; }
}
</style>
