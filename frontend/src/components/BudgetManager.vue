<!-- src/components/BudgetManager.vue -->
<template>
  <el-card>
    <template #header>🎯 预算设置</template>

    <!-- 月份选择器 -->
    <el-date-picker
      v-model="selectedMonth"
      type="month"
      value-format="YYYY-MM"
      placeholder="选择月份"
      style="margin-bottom: 10px;"
      @change="fetchBudgets"
    />

    <!-- 当前月份提示 -->
    <p style="margin: 10px 0; color: #888;">
      当前查看月份：{{ selectedMonth }}，所有预算为该月有效。
    </p>

    <!-- 输入新预算 -->
    <div>
      <el-input
        v-model="newBudget.category"
        placeholder="分类"
        style="width: 30%;"
      />
      <el-input
        v-model.number="newBudget.amount"
        placeholder="金额"
        style="width: 30%; margin-left: 10px;"
      />
      <el-button type="primary" size="small" @click="addOrUpdateBudget">设置</el-button>
    </div>

    <!-- 预算列表 -->
    <el-table :data="budgets" style="margin-top: 10px">
      <el-table-column prop="category" label="分类" />
      <el-table-column prop="amount" label="预算金额" />
      <el-table-column prop="remaining" label="剩余预算" />
    </el-table>

    <!-- 底部说明 -->
    <p style="margin-top: 10px; font-size: 13px; color: #999;">
      每月 1 日预算将自动重置，请记得每月重新设置预算。
    </p>
  </el-card>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import api from '@/api'

const props = defineProps({ refreshFlag: Number })
const budgets = ref([])
const newBudget = ref({ category: '', amount: '', cycle: '月' })

// 当前月份（例如 "2025-06"）
const currentMonth = new Date().toISOString().slice(0, 7)
const selectedMonth = ref(currentMonth)

async function fetchBudgets() {
  const res = await api.get('/api/budgets', {
    params: { month: selectedMonth.value }
  })
  budgets.value = res.data
}

async function addOrUpdateBudget() {
  if (!newBudget.value.category || !newBudget.value.amount) return
  await api.post('/api/budgets', {
    ...newBudget.value,
    month: selectedMonth.value
  })
  newBudget.value = { category: '', amount: '', cycle: '月' }
  await fetchBudgets()
}

onMounted(fetchBudgets)
watch(() => props.refreshFlag, fetchBudgets)
</script>




