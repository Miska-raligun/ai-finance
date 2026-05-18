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
    <VChart
      v-else
      theme="animal"
      :option="option"
      autoresize
      style="width: 100%; height: 240px"
    />

    <div v-if="hasData" class="cal-summary">
      共 {{ rows.length }} 天有支出 · 总额
      <strong>¥{{ totalSpend.toFixed(2) }}</strong> · 单日最高
      <strong>¥{{ maxSpend.toFixed(2) }}</strong>
    </div>
  </el-card>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
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
const rows = ref([])    // [{date, expense, income}]

const hasData = computed(() => rows.value.some(r => r.expense > 0))
const totalSpend = computed(() => rows.value.reduce((s, r) => s + (r.expense || 0), 0))
const maxSpend = computed(() => rows.value.reduce((m, r) => Math.max(m, r.expense || 0), 0))

// 日历范围：从今天往回 N-1 天
const rangeEnd = computed(() => {
  const d = new Date()
  return d.toISOString().slice(0, 10)
})
const rangeStart = computed(() => {
  const d = new Date()
  d.setDate(d.getDate() - (days.value - 1))
  return d.toISOString().slice(0, 10)
})

const option = computed(() => ({
  tooltip: {
    formatter: (p) => {
      if (!p.value || !p.value[0]) return ''
      const d = p.value[0]
      const v = p.value[1]
      return `${d}<br/>支出 ¥${Number(v).toFixed(2)}`
    },
  },
  visualMap: {
    min: 0,
    max: Math.max(50, maxSpend.value),
    type: 'continuous',
    orient: 'horizontal',
    left: 'center',
    bottom: 0,
    itemWidth: 12,
    itemHeight: 100,
    text: ['高', '低'],
    textStyle: { color: '#725d42', fontSize: 11 },
    inRange: {
      // 动森色板：浅米 → 薄荷 → 薄荷深，0 值用近底色淡化
      color: ['#f0ece2', '#cbf0eb', '#80dfd6', '#19c8b9', '#11a89b'],
    },
    formatter: (v) => '¥' + Number(v).toFixed(0),
  },
  calendar: {
    range: [rangeStart.value, rangeEnd.value],
    cellSize: ['auto', 14],
    left: 36,
    right: 16,
    top: 18,
    bottom: 60,
    splitLine: { show: false },
    itemStyle: { borderWidth: 2, borderColor: 'var(--color-bg, #f8f8f0)', color: '#f8f8f0' },
    yearLabel: { show: false },
    monthLabel: {
      color: '#9f927d', fontWeight: 600, fontSize: 11,
      nameMap: ['1月', '2月', '3月', '4月', '5月', '6月',
                '7月', '8月', '9月', '10月', '11月', '12月'],
    },
    dayLabel: {
      color: '#9f927d', fontSize: 10, firstDay: 1,
      nameMap: ['日', '一', '二', '三', '四', '五', '六'],
    },
  },
  series: [{
    type: 'heatmap',
    coordinateSystem: 'calendar',
    data: rows.value.map(r => [r.date, r.expense]),
  }],
}))

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

// 数据变化时也刷新（如新增记录后）
import { watch } from 'vue'
watch(() => props.refreshFlag, fetchData)
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
.cal-summary {
  margin-top: 12px;
  padding: 8px 12px;
  background: var(--color-surface-2);
  border-radius: 10px;
  font-size: 12px;
  color: var(--color-text);
  text-align: center;
}
.cal-summary strong {
  color: var(--color-primary-dark);
  font-weight: 800;
  margin: 0 2px;
}
</style>
