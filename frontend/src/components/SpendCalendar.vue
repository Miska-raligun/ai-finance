<template>
  <el-card>
    <template #header>
      <div class="cal-header">
        <span>📅 支出热力日历</span>
        <el-radio-group v-model="days" size="small" @change="fetchData">
          <el-radio-button :value="90">90 天</el-radio-button>
          <el-radio-button :value="180">半年</el-radio-button>
          <el-radio-button :value="365">一年</el-radio-button>
        </el-radio-group>
      </div>
    </template>

    <div v-if="loading" class="cal-loading">加载中…</div>
    <EmptyHint
      v-else-if="!hasData"
      kind="tent"
      title="还没有支出记录"
      hint="录几笔记账之后，这里会按每天支出强度铺色块。"
    />
    <template v-else>
      <VChart
        ref="chartRef"
        theme="animal"
        :option="option"
        autoresize
        :style="{ width: '100%', height: chartHeight + 'px' }"
        @click="onCellClick"
      />

      <div class="cal-stats">
        <div class="cal-stat-pill">
          <span class="cal-stat-label">活跃天</span>
          <span class="cal-stat-value">{{ activeDays }}</span>
        </div>
        <div class="cal-stat-pill">
          <span class="cal-stat-label">总支出</span>
          <span class="cal-stat-value">¥{{ totalSpend.toFixed(0) }}</span>
        </div>
        <div class="cal-stat-pill">
          <span class="cal-stat-label">日均</span>
          <span class="cal-stat-value">¥{{ avgSpend.toFixed(0) }}</span>
        </div>
        <div class="cal-stat-pill cal-stat-max">
          <span class="cal-stat-label">单日峰</span>
          <span class="cal-stat-value">¥{{ maxSpend.toFixed(0) }}</span>
        </div>
      </div>
    </template>

    <!-- 当天明细弹窗 -->
    <el-dialog
      v-model="detail.visible"
      :title="detail.title"
      :width="dialogWidth"
      append-to-body
    >
      <div v-if="detail.loading" class="detail-loading">加载中…</div>
      <div v-else>
        <div class="detail-summary">
          <div class="detail-row">
            <span>💸 支出</span>
            <strong class="detail-spend">¥{{ detail.spendTotal.toFixed(2) }}</strong>
          </div>
          <div class="detail-row">
            <span>💰 收入</span>
            <strong class="detail-income">¥{{ detail.incomeTotal.toFixed(2) }}</strong>
          </div>
          <div class="detail-row">
            <span>净额</span>
            <strong :class="detail.net >= 0 ? 'detail-up' : 'detail-down'">
              {{ detail.net >= 0 ? '+' : '−' }}¥{{ Math.abs(detail.net).toFixed(2) }}
            </strong>
          </div>
        </div>

        <div v-if="!detail.items.length" class="detail-empty">这一天没有记录。</div>
        <div v-else class="detail-list">
          <div
            v-for="(it, idx) in detail.items" :key="idx"
            class="detail-item" :class="it.type"
          >
            <span class="detail-cat">{{ it.category }}</span>
            <span class="detail-amt">
              {{ it.type === 'expense' ? '−' : '+' }}¥{{ it.amount.toFixed(2) }}
            </span>
            <span v-if="it.note" class="detail-note">{{ it.note }}</span>
          </div>
        </div>
      </div>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import api from '@/api'
import { use } from 'echarts/core'
import VChart from 'vue-echarts'
import { HeatmapChart } from 'echarts/charts'
import {
  TooltipComponent, VisualMapComponent, CalendarComponent, TitleComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import EmptyHint from '@/components/EmptyHint.vue'

use([HeatmapChart, TooltipComponent, VisualMapComponent, CalendarComponent,
     TitleComponent, CanvasRenderer])

const props = defineProps({ refreshFlag: { type: Number, default: 0 } })

const days = ref(90)
const loading = ref(false)
const rows = ref([])
const chartRef = ref(null)

const hasData = computed(() => rows.value.some(r => r.expense > 0))
const totalSpend = computed(() => rows.value.reduce((s, r) => s + (r.expense || 0), 0))
const maxSpend = computed(() => rows.value.reduce((m, r) => Math.max(m, r.expense || 0), 0))
const activeDays = computed(() => rows.value.filter(r => (r.expense || 0) > 0).length)
const avgSpend = computed(() => activeDays.value ? totalSpend.value / activeDays.value : 0)

// 日历高度按 days 自动适配：90 天 ~3 个月 1 行；半年 2 行；1 年 3 行
const chartHeight = computed(() => {
  if (days.value <= 100) return 180
  if (days.value <= 200) return 230
  return 260
})

const rangeEnd = computed(() => new Date().toISOString().slice(0, 10))
const rangeStart = computed(() => {
  const d = new Date()
  d.setDate(d.getDate() - (days.value - 1))
  return d.toISOString().slice(0, 10)
})

const option = computed(() => ({
  tooltip: {
    trigger: 'item',
    formatter: (p) => {
      if (!p.value || !p.value[0]) return ''
      const [d, v] = p.value
      const inc = (rows.value.find(r => r.date === d) || {}).income || 0
      return `<div style="font-weight:700;margin-bottom:4px">${d}</div>` +
             `💸 支出 ¥${Number(v).toFixed(2)}` +
             (inc > 0 ? `<br/>💰 收入 ¥${inc.toFixed(2)}` : '') +
             `<div style="font-size:11px;color:#9f927d;margin-top:4px">点击查看明细 →</div>`
    },
  },
  visualMap: {
    min: 0,
    max: Math.max(50, maxSpend.value),
    type: 'piecewise',     // 改用分段更直观
    pieces: _piecewise(maxSpend.value),
    orient: 'horizontal',
    left: 'center',
    bottom: 4,
    itemWidth: 18,
    itemHeight: 12,
    itemGap: 6,
    textGap: 4,
    textStyle: { color: '#725d42', fontSize: 11, fontWeight: 600 },
    showLabel: false,      // 单独显示极值标签更好看
  },
  calendar: {
    range: [rangeStart.value, rangeEnd.value],
    cellSize: ['auto', 18],
    left: 36,
    right: 12,
    top: 28,
    bottom: 50,
    splitLine: {
      show: true,
      lineStyle: { color: '#e0d6bf', width: 1, type: 'solid' },
    },
    itemStyle: {
      borderWidth: 3,
      borderColor: 'var(--color-bg, #f8f8f0)',  // 间隙融入背景
      borderRadius: 4,
      color: '#ece0c4',                          // 0 值用沙色，比白色更协调
    },
    yearLabel: { show: false },
    monthLabel: {
      color: '#794f27',
      fontWeight: 700,
      fontSize: 11,
      margin: 6,
      nameMap: ['1月', '2月', '3月', '4月', '5月', '6月',
                '7月', '8月', '9月', '10月', '11月', '12月'],
    },
    dayLabel: {
      color: '#9f927d',
      fontSize: 10,
      margin: 8,
      firstDay: 1,
      nameMap: ['日', '一', '二', '三', '四', '五', '六'],
    },
  },
  series: [{
    type: 'heatmap',
    coordinateSystem: 'calendar',
    data: rows.value.map(r => [r.date, r.expense]),
    itemStyle: {
      borderRadius: 4,
      borderWidth: 3,
      borderColor: 'var(--color-bg, #f8f8f0)',
    },
    emphasis: {
      itemStyle: {
        borderColor: '#11a89b',
        borderWidth: 2,
        shadowBlur: 6,
        shadowColor: 'rgba(17, 168, 155, 0.45)',
      },
    },
  }],
}))

// 5 段动森色阶 — 自适应当前最大值
function _piecewise(max) {
  const m = Math.max(50, max)
  return [
    { value: 0, label: '无', color: '#ece0c4' },
    { min: 0.01, max: m * 0.2,  label: '少',  color: '#d4f0eb' },
    { min: m * 0.2,  max: m * 0.5, label: '中', color: '#82dfd2' },
    { min: m * 0.5,  max: m * 0.8, label: '多', color: '#19c8b9' },
    { min: m * 0.8, label: '高', color: '#0a8a7e' },
  ]
}

async function fetchData() {
  loading.value = true
  try {
    const res = await api.get('/api/stats/calendar', {
      params: { days: days.value },
      silent: true,
    })
    rows.value = res.data?.data || []
  } catch {
    rows.value = []
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)
watch(() => props.refreshFlag, fetchData)

// ===== 点击单元格弹出当天明细 =====
const _mq = window.matchMedia('(max-width: 768px)')
const isMobile = ref(_mq.matches)
function _onMq(e) { isMobile.value = e.matches }
onMounted(() => _mq.addEventListener('change', _onMq))
onBeforeUnmount(() => _mq.removeEventListener('change', _onMq))
const dialogWidth = computed(() => isMobile.value ? 'calc(100vw - 28px)' : '480px')

const detail = ref({
  visible: false,
  title: '',
  loading: false,
  items: [],
  spendTotal: 0,
  incomeTotal: 0,
  net: 0,
})

function onCellClick(params) {
  const d = params?.value?.[0]
  if (!d) return
  openDayDetail(d)
}

async function openDayDetail(dateStr) {
  detail.value.visible = true
  detail.value.title = `${dateStr} · 收支明细`
  detail.value.loading = true
  detail.value.items = []
  try {
    // 同一天的支出 + 收入
    const [eRes, iRes] = await Promise.all([
      api.get('/api/records', {
        params: { start_date: dateStr, end_date: dateStr, limit: 100 },
        silent: true,
      }),
      api.get('/api/income', {
        params: { start_date: dateStr, end_date: dateStr, limit: 100 },
        silent: true,
      }),
    ])
    const expenses = (eRes.data?.data || []).map(r => ({
      type: 'expense', category: r.category, amount: r.amount, note: r.note,
    }))
    const incomes = (iRes.data?.data || []).map(r => ({
      type: 'income', category: r.category, amount: r.amount, note: r.note,
    }))
    detail.value.items = [...expenses, ...incomes]
    detail.value.spendTotal = expenses.reduce((s, r) => s + r.amount, 0)
    detail.value.incomeTotal = incomes.reduce((s, r) => s + r.amount, 0)
    detail.value.net = detail.value.incomeTotal - detail.value.spendTotal
  } catch {
    detail.value.items = []
  } finally {
    detail.value.loading = false
  }
}
</script>

<style scoped>
.cal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.cal-loading {
  text-align: center;
  padding: 60px 0;
  color: var(--color-text-muted);
  font-size: 13px;
}
.cal-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-top: 12px;
}
.cal-stat-pill {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 8px 4px;
  background: var(--color-surface-2);
  border-radius: 12px;
  box-shadow: inset 0 -2px 0 rgba(0, 0, 0, 0.04);
}
.cal-stat-pill.cal-stat-max {
  background: var(--color-primary-light);
}
.cal-stat-label {
  font-size: 10px;
  color: var(--color-text-muted);
  font-weight: 600;
}
.cal-stat-value {
  font-size: 14px;
  font-weight: 800;
  color: var(--color-text-strong);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
}

/* 当天明细弹窗 */
.detail-loading, .detail-empty {
  text-align: center;
  padding: 30px 0;
  color: var(--color-text-muted);
  font-size: 13px;
}
.detail-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}
.detail-row {
  flex: 1 1 100px;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 8px;
  background: var(--color-surface-2);
  border-radius: 12px;
  font-size: 11px;
  color: var(--color-text-muted);
}
.detail-row strong {
  font-size: 16px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  margin-top: 2px;
}
.detail-spend { color: var(--color-up); }
.detail-income { color: var(--color-down); }
.detail-up { color: var(--color-down); }
.detail-down { color: var(--color-up); }

.detail-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 360px;
  overflow-y: auto;
}
.detail-item {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 4px 12px;
  align-items: center;
  padding: 8px 12px;
  border-radius: 10px;
  background: var(--color-surface);
  border-left: 3px solid var(--color-border);
  font-size: 13px;
}
.detail-item.expense { border-left-color: var(--color-up); }
.detail-item.income  { border-left-color: var(--color-down); }
.detail-cat {
  font-weight: 700;
  color: var(--color-text-strong);
}
.detail-amt {
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.detail-item.expense .detail-amt { color: var(--color-up); }
.detail-item.income  .detail-amt { color: var(--color-down); }
.detail-note {
  grid-column: 1 / -1;
  font-size: 11px;
  color: var(--color-text-muted);
  word-break: break-word;
}

/* 极窄屏挤一点：4 列 → 2 列 */
@media (max-width: 420px) {
  .cal-stats { grid-template-columns: repeat(2, 1fr); }
}
</style>
