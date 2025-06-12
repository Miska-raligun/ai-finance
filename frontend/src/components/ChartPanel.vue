<!-- components/ChartPanel.vue -->
<template>
  <el-card>
    <template #header>
      📊 收支图表分析
    </template>

    <div class="toolbar">
      <el-radio-group v-model="mode">
        <el-radio-button label="month">按月</el-radio-button>
        <el-radio-button label="year">按年</el-radio-button>
      </el-radio-group>
      <el-date-picker
        v-model="selectedTime"
        :type="mode === 'month' ? 'month' : 'year'"
        :value-format="mode === 'month' ? 'YYYY-MM' : 'YYYY'"
        @change="fetchChartData"
      />
      <el-button class="ml" @click="showAll">查看全部</el-button>
    </div>

    <div class="chart-row">
      <VChart :option="incomePieOption" style="height: 300px; flex: 1" />
      <VChart :option="spendPieOption" style="height: 300px; flex: 1" />
    </div>
    <VChart :option="lineOption" style="height: 300px" />
  </el-card>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
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

use([
  PieChart,
  LineChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  CanvasRenderer
])
const props = defineProps({ refreshFlag: Number })
const mode = ref('month')
const selectedTime = ref()
const incomePieOption = ref({})
const spendPieOption = ref({})
const lineOption = ref({})

function showAll() {
  mode.value = 'year'
  selectedTime.value = ''
  fetchChartData()
}

const fetchChartData = async () => {
  if (!selectedTime.value && mode.value === 'month') return

  const time = selectedTime.value
  const catParams = {}
  if (mode.value === 'month' && time) {
    catParams.month = time
  } else if (mode.value === 'year' && time) {
    catParams.year = time
  }
  const [cats, trend] = await Promise.all([
    api.get('/api/stats/by-category', { params: catParams }),
    mode.value === 'month'
      ? api.get('/api/stats/daily', { params: { month: time } })
      : api.get('/api/stats/monthly', { params: time ? { year: time } : {} })
  ])

  const incomeCats = cats.data.filter(x => x['类型'] === '收入')
  const spendCats = cats.data.filter(x => x['类型'] === '支出')

  incomePieOption.value = {
    title: { text: '收入分布', left: 'center' },
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, left: 'center' },
    series: [
      {
        name: '收入来源',
        type: 'pie',
        radius: '50%',
        data: incomeCats.map(x => ({ name: x['名称'], value: x['金额'] }))
      }
    ]
  }
  spendPieOption.value = {
    title: { text: '支出分布', left: 'center' },
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, left: 'center' },
    series: [
      {
        name: '消费分类',
        type: 'pie',
        radius: '50%',
        data: spendCats.map(x => ({ name: x['名称'], value: x['金额'] }))
      }
    ]
  }

  if (mode.value === 'month') {
    lineOption.value = {
      title: { text: '本月每日收支情况' },
      tooltip: { trigger: 'axis' },
      legend: { data: ['收入', '支出', '结余'] },
      xAxis: { type: 'category', data: trend.data.map(d => d.date) },
      yAxis: { type: 'value' },
      series: [
        { name: '收入', type: 'line', data: trend.data.map(d => d['收入']) },
        { name: '支出', type: 'line', data: trend.data.map(d => d['支出']) },
        { name: '结余', type: 'line', data: trend.data.map(d => d['结余']) }
      ]
    }
  } else {
    lineOption.value = {
      title: { text: '年度收支趋势' },
      tooltip: { trigger: 'axis' },
      legend: { data: ['收入', '支出', '结余'] },
      xAxis: { type: 'category', data: trend.data.map(m => m.month) },
      yAxis: { type: 'value' },
      series: [
        { name: '收入', type: 'line', data: trend.data.map(m => m['收入']) },
        { name: '支出', type: 'line', data: trend.data.map(m => m['支出']) },
        { name: '结余', type: 'line', data: trend.data.map(m => m['收入'] - m['支出']) }
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
  // 清空选择以避免格式不匹配
  selectedTime.value = mode.value === 'month'
    ? new Date().toISOString().slice(0, 7)
    : new Date().getFullYear().toString()
  fetchChartData()
})
</script>

<style scoped>
.v-chart {
  width: 100%;
}
.toolbar {
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.toolbar .ml {
  margin-left: 10px;
}
.chart-row {
  display: flex;
  gap: 20px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
@media (max-width: 600px) {
  .chart-row {
    flex-direction: column;
  }
}
</style>

