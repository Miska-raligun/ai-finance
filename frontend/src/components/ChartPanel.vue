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
        <VChart :option="incomePieOption" style="height: 280px; width: 100%" autoresize />
      </div>
      <div class="pie-wrap">
        <VChart :option="spendPieOption" style="height: 280px; width: 100%" autoresize />
      </div>
    </div>

    <VChart :option="lineOption" style="height: 280px; width: 100%" autoresize />
  </el-card>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import api from '@/api'
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
const incomePieOption = ref({})
const spendPieOption = ref({})
const lineOption = ref({})
const totalIncome = ref(0)
const totalExpense = ref(0)
const totalBalance = computed(() => totalIncome.value - totalExpense.value)
const incomeChangePct = ref(null)
const expenseChangePct = ref(null)
const balanceChangePct = ref(null)
const fmtNum = v => Math.abs(v).toFixed(2)

const PRIMARY = '#4F46E5'
// 高对比度调色板：色相均匀分布，相邻色差足够大
const PALETTE = ['#4F46E5','#F59E0B','#EF4444','#22C55E','#0EA5E9','#EC4899','#F97316','#14B8A6','#8B5CF6','#84CC16']

function showAll() {
  mode.value = 'year'
  selectedTime.value = ''
  fetchChartData()
}

const fetchChartData = async () => {
  if (!selectedTime.value && mode.value === 'month') return
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
  // 月度模式时同时拉取环比对比数据
  if (mode.value === 'month' && time) {
    requests.push(api.get('/api/stats/comparison', { params: { month: time } }))
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

  const makePie = (title, data, seriesName) => ({
    color: PALETTE,
    title: { text: title, left: 'center', top: 6, textStyle: { fontSize: 13, fontWeight: 600, color: '#1e293b' } },
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
    color: [PRIMARY, '#EF4444', '#22C55E'],
    legend: { data: ['收入', '支出', '结余'], bottom: 0, left: 'center', textStyle: { fontSize: 12 } },
    grid: { top: 36, bottom: 50, left: 50, right: 16 },
    tooltip: lineTooltip,
    xAxis: { type: 'category', axisLine: { lineStyle: { color: '#e2e8f0' } }, axisLabel: { color: '#64748b', fontSize: 11 } },
    yAxis: { type: 'value', axisLabel: { color: '#64748b', fontSize: 11 }, splitLine: { lineStyle: { color: '#f1f5f9' } } },
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
  background: #EFF6FF;
}
.stat-item.income  { background: #F0FDF4; }
.stat-item.expense { background: #FFF1F2; }
.stat-item.balance-pos { background: #EFF6FF; }
.stat-item.balance-neg { background: #FFF7ED; }
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
.balance-pos .stat-value { color: #2563EB; }
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
  background: #FAFBFF;
  border-radius: 8px;
  padding: 4px;
}

@media (max-width: 768px) {
  .chart-row { flex-direction: column; }
  .pie-wrap { flex: none; width: 100%; }
}
</style>
