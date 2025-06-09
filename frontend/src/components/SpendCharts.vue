<!-- src/components/SpendCharts.vue -->
<template>
  <el-card>
    <template #header>
      📊 消费图表
    </template>

    <el-form
    :inline="true"
    size="small"
    style="margin-bottom: 10px; display: flex; align-items: center; gap: 10px;"
    >
    <el-form-item label="月份">
        <el-date-picker
        v-model="selectedMonth"
        type="month"
        value-format="YYYY-MM"
        placeholder="选择月份"
        clearable
        style="width: 150px"
        />
    </el-form-item>

    <el-form-item>
        <el-button type="primary" @click="drawChart">查看</el-button>
    </el-form-item>

    <el-form-item>
        <el-button @click="resetMonth">查看全部</el-button>
    </el-form-item>
    </el-form>

    <div class="chart-wrapper" style="height: 400px;">
      <canvas ref="chartRef"></canvas>
    </div>
  </el-card>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import axios from 'axios'
import Chart from 'chart.js/auto'

const props = defineProps({ refreshFlag: Number })

const chartRef = ref(null)
const selectedMonth = ref('') // 当前选中的月份
let chartInstance = null

function resetMonth() {
  selectedMonth.value = ''
  drawChart()
}

async function drawChart() {
  const res = await axios.get('/records', {
    params: selectedMonth.value ? { month: selectedMonth.value } : {}
  })
  const data = res.data

  // 分组
  const grouped = {}
  for (const item of data) {
    grouped[item.category] = (grouped[item.category] || 0) + item.amount
  }

  const labels = Object.keys(grouped)
  const amounts = Object.values(grouped)

  if (chartInstance) chartInstance.destroy()
  chartInstance = new Chart(chartRef.value.getContext('2d'), {
    type: 'pie',
    data: {
      labels,
      datasets: [{ data: amounts }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: {
        padding: 40
      },
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            boxWidth: 10,
            padding: 10,
            font: {
              size: 12
            }
          }
        }
      }
    }
  })
}

onMounted(drawChart)
watch(() => props.refreshFlag, drawChart)
</script>




