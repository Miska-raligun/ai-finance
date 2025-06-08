<!-- src/components/SpendCharts.vue -->
<template>
  <el-card>
    <template #header>📊 消费图表</template>
    <div class="chart-wrapper">
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
let chartInstance = null

async function drawChart() {
  const res = await axios.get('/records')
  const data = res.data

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


