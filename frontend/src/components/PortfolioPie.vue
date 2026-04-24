<template>
  <el-card>
    <template #header>🥧 资产配置</template>
    <div v-if="!hasData" class="empty">暂无持仓数据，先添加几项资产吧。</div>
    <div v-else class="chart-wrapper" style="height: 320px;">
      <canvas ref="chartRef"></canvas>
    </div>
    <div v-if="hasData" class="legend">
      <div v-for="row in byType" :key="row.type" class="legend-item">
        <span class="dot" :style="{ background: colorOf(row.type) }"></span>
        <span class="label">{{ typeLabel(row.type) }}</span>
        <span class="value">¥{{ row.value.toFixed(2) }}</span>
        <span class="pct">{{ row.pct.toFixed(1) }}%</span>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import Chart from 'chart.js/auto'

const props = defineProps({
  allocation: { type: Object, default: () => null },
})

const chartRef = ref(null)
let chartInstance = null

const byType = computed(() => props.allocation?.by_type || [])
const hasData = computed(() => byType.value.length > 0 && byType.value.some(r => r.value > 0))

// 类型现在由用户自管理，直接显示后端给的 type 字符串，颜色按名字 hash 分配
function typeLabel(t) { return t || '未分类' }

const PALETTE = ['#2563EB', '#60A5FA', '#22C55E', '#F59E0B', '#EF4444', '#8B5CF6', '#14B8A6']
function hashStr(s) {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) & 0x7fffffff
  return h
}
function colorOf(t) { return PALETTE[hashStr(String(t || '')) % PALETTE.length] }

function draw() {
  if (!chartRef.value) return
  const labels = byType.value.map(r => typeLabel(r.type))
  const data = byType.value.map(r => r.value)
  const colors = byType.value.map(r => colorOf(r.type))

  if (chartInstance) chartInstance.destroy()
  if (!hasData.value) return

  chartInstance = new Chart(chartRef.value.getContext('2d'), {
    type: 'doughnut',
    data: { labels, datasets: [{ data, backgroundColor: colors, borderWidth: 0 }] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '60%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.label}：¥${ctx.parsed.toFixed(2)}`,
          },
        },
      },
    },
  })
}

watch(() => props.allocation, draw, { deep: true })
onMounted(draw)
onBeforeUnmount(() => { if (chartInstance) chartInstance.destroy() })
</script>

<style scoped>
.empty {
  text-align: center;
  color: var(--color-text-muted);
  padding: 40px 0;
}
.legend {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: var(--color-text);
}
.dot {
  width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
}
.label { flex: 1; }
.value { color: var(--color-text-muted); font-variant-numeric: tabular-nums; }
.pct {
  width: 54px;
  text-align: right;
  color: var(--color-primary);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
</style>
