<template>
  <el-card>
    <template #header>
      <div class="sk-header">
        <span>🌊 收支流向</span>
        <el-date-picker
          v-model="month"
          type="month"
          format="YYYY-MM"
          value-format="YYYY-MM"
          size="small"
          @change="fetchData"
          style="width: 150px"
        />
      </div>
    </template>

    <div v-if="loading" class="sk-loading">加载中…</div>
    <EmptyHint
      v-else-if="!hasData"
      kind="island"
      title="本月还没有现金流"
      hint="先在「聊天记账」里记上几笔，桑基图就会显示资金的来去。"
    />
    <VChart
      v-else
      theme="animal"
      :option="option"
      autoresize
      style="width: 100%; height: 280px"
    />
  </el-card>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/api'
import { use } from 'echarts/core'
import VChart from 'vue-echarts'
import { SankeyChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import EmptyHint from '@/components/EmptyHint.vue'

use([SankeyChart, TooltipComponent, CanvasRenderer])

const props = defineProps({ refreshFlag: { type: Number, default: 0 } })

const month = ref(new Date().toISOString().slice(0, 7))
const loading = ref(false)
const income = ref([])   // [{名称, 金额, 类型: '收入'}]
const expense = ref([])

const totalIncome = computed(() => income.value.reduce((s, x) => s + x['金额'], 0))
const totalExpense = computed(() => expense.value.reduce((s, x) => s + x['金额'], 0))
const balance = computed(() => totalIncome.value - totalExpense.value)

const hasData = computed(() => totalIncome.value > 0 || totalExpense.value > 0)

// 节点 / 链接构造：
//   收入分类 → 总现金池 → 支出分类 + (结余/赤字)
const option = computed(() => {
  const PALETTE = ['#19c8b9', '#f8a6b2', '#f7cd67', '#82d5bb', '#b77dee',
                   '#889df0', '#e59266', '#8ac68a', '#fc736d', '#d1da49']
  const POOL = '现金池'
  const SURPLUS = '结余'
  const DEFICIT = '赤字'

  const nodes = []
  const links = []

  // 收入分类节点
  income.value.forEach((x, i) => {
    nodes.push({ name: x['名称'], itemStyle: { color: PALETTE[i % PALETTE.length] } })
    links.push({ source: x['名称'], target: POOL, value: x['金额'] })
  })

  // 中心池
  nodes.push({ name: POOL, itemStyle: { color: '#11a89b' } })

  // 支出分类
  expense.value.forEach((x, i) => {
    nodes.push({ name: x['名称'] + ' ', itemStyle: { color: PALETTE[(i + 5) % PALETTE.length] } })
    // 加空格区分同名（如"餐饮" 既是支出名也可能是收入名）
    links.push({ source: POOL, target: x['名称'] + ' ', value: x['金额'] })
  })

  // 结余 / 赤字
  if (balance.value >= 0.5) {
    nodes.push({ name: SURPLUS, itemStyle: { color: '#86d67a' } })
    links.push({ source: POOL, target: SURPLUS, value: balance.value })
  } else if (balance.value <= -0.5) {
    nodes.push({ name: DEFICIT, itemStyle: { color: '#e05a5a' } })
    // 赤字：从"补足"节点流向池子，用 income 池 = expense 平衡。
    // 简化：单独画一条 deficit→pool 链
    nodes.push({ name: '透支补足', itemStyle: { color: '#e05a5a' } })
    links.push({ source: '透支补足', target: POOL, value: Math.abs(balance.value) })
  }

  return {
    tooltip: {
      trigger: 'item',
      formatter: (p) => {
        if (p.dataType === 'edge') {
          return `${p.data.source} → ${p.data.target}<br/>¥${p.data.value.toFixed(2)}`
        }
        return `${p.name}`
      },
    },
    series: [{
      type: 'sankey',
      data: nodes,
      links,
      layout: 'none',
      orient: 'horizontal',
      left: 6,
      right: 70,
      top: 14,
      bottom: 14,
      nodeAlign: 'justify',
      nodeWidth: 14,
      nodeGap: 8,
      lineStyle: {
        color: 'gradient',
        curveness: 0.55,
        opacity: 0.55,
      },
      label: {
        color: '#725d42',
        fontWeight: 600,
        fontSize: 11,
        formatter: (p) => p.name.replace(/\s+$/, ''),  // 去掉空格后缀
      },
      emphasis: { focus: 'adjacency' },
    }],
  }
})

async function fetchData() {
  loading.value = true
  try {
    const res = await api.get('/api/stats/by-category', {
      params: { month: month.value },
      silent: true,
    })
    const data = res.data || []
    income.value = data.filter(x => x['类型'] === '收入')
    expense.value = data.filter(x => x['类型'] === '支出')
  } catch {
    income.value = []
    expense.value = []
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)

import { watch } from 'vue'
watch(() => props.refreshFlag, fetchData)
</script>

<style scoped>
.sk-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.sk-loading {
  text-align: center;
  padding: 80px 0;
  color: var(--color-text-muted);
  font-size: 13px;
}
</style>
