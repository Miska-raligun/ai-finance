<!-- components/ChartPanel.vue -->
<template>
  <el-card>
    <template #header>
      📊 收支图表分析
    </template>

    <div style="margin-bottom: 10px">
      <el-radio-group v-model="mode">
        <el-radio-button label="month">按月</el-radio-button>
        <el-radio-button label="year">按年</el-radio-button>
      </el-radio-group>
      <el-date-picker
        v-model="selectedTime"
        :type="mode === 'month' ? 'month' : 'year'"
        value-format="YYYY-MM"
        style="margin-left: 10px"
        @change="fetchChartData"
      />
    </div>

    <div>
      <v-chart :option="pieOption" style="height: 300px" />
      <v-chart :option="lineOption" style="height: 300px; margin-top: 20px" />
    </div>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
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

const mode = ref('month')
const selectedTime = ref()
const pieOption = ref({})
const lineOption = ref({})

const fetchChartData = async () => {
  if (!selectedTime.value) return

  const time = selectedTime.value
  const [cats, trend] = await Promise.all([
    axios.get('/stats/by-category'),
    mode.value === 'month'
      ? axios.get('/stats/daily', { params: { month: time } })
      : axios.get('/stats/monthly')
  ])

  const incomeCats = cats.data.filter(x => x['类型'] === '收入')
  const spendCats = cats.data.filter(x => x['类型'] === '支出')

  pieOption.value = {
    title: [{ text: '收入分布', left: '25%' }, { text: '支出分布', left: '75%' }],
    tooltip: { trigger: 'item' },
    legend: { bottom: 10 },
    series: [
      {
        name: '收入来源',
        type: 'pie',
        radius: '40%',
        center: ['25%', '50%'],
        data: incomeCats.map(x => ({ name: x['名称'], value: x['金额'] }))
      },
      {
        name: '消费分类',
        type: 'pie',
        radius: '40%',
        center: ['75%', '50%'],
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
</script>

<style scoped>
.v-chart {
  width: 100%;
}
</style>

