<!-- src/components/BudgetManager.vue -->
<template>
  <el-card>
    <template #header>🎯 预算设置</template>
    <div>
      <el-input v-model="newBudget.category" placeholder="分类" style="width: 30%;" />
      <el-input v-model.number="newBudget.amount" placeholder="金额" style="width: 30%; margin-left: 10px;" />
      <el-button type="primary" @click="addOrUpdateBudget">设置</el-button>
    </div>
    <el-table :data="budgets" style="margin-top: 10px">
      <el-table-column prop="category" label="分类" />
      <el-table-column prop="amount" label="预算金额" />
    </el-table>
  </el-card>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import axios from 'axios'
const props = defineProps({ refreshFlag: Number })

const budgets = ref([])
const newBudget = ref({ category: '', amount: '', cycle: '月' })

async function fetchBudgets() {
  const res = await axios.get('/budgets')
  budgets.value = res.data
}

async function addOrUpdateBudget() {
  if (!newBudget.value.category || !newBudget.value.amount) return
  await axios.post('/budgets', newBudget.value)
  newBudget.value = { category: '', amount: '', cycle: '月' }
  await fetchBudgets()
}

onMounted(fetchBudgets)
watch(() => props.refreshFlag, fetchBudgets)
</script>


