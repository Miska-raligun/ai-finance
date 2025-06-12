<template>
  <el-card>
    <template #header>
      预算管理和分类管理
    </template>

    <!-- 月份选择 -->
    <el-form :inline="true" size="small" class="mb-2 form-row">
      <el-form-item label="选择月份">
        <el-date-picker
          v-model="selectedMonth"
          type="month"
          value-format="YYYY-MM"
          placeholder="选择月份"
          @change="fetchBudgets"
        />
      </el-form-item>
    </el-form>

    <!-- 预算表 -->
    <el-table
      :data="budgets"
      size="small"
      border
      class="mb-3"
      style="width: 100%"
    >
      <el-table-column prop="category" label="分类" />
      <el-table-column prop="amount" label="预算额">
        <template #default="scope">{{ Number(scope.row.amount).toFixed(2) }}</template>
      </el-table-column>
      <el-table-column prop="remaining" label="剩余预算">
        <template #default="scope">{{ Number(scope.row.remaining).toFixed(2) }}</template>
      </el-table-column>
    </el-table>

    <!-- 添加/更新预算 -->
    <el-form :inline="true" size="small" class="mb-3 form-row">
      <el-form-item label="分类">
        <el-select v-model="budgetForm.category" placeholder="选择分类">
          <el-option
            v-for="cat in expenseCategories"
            :key="cat"
            :label="cat"
            :value="cat"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="预算">
        <el-input-number v-model="budgetForm.amount" :min="0" />
      </el-form-item>
      <el-button type="primary" size="small" @click="submitBudget">确定</el-button>
    </el-form>

    <el-divider />

    <!-- 分类管理 -->
    <el-tabs v-model="activeTab">
      <el-tab-pane label="支出分类" name="支出">
        <CategoryManager
          type="expense"
          :refresh-flag="props.refreshFlag"
          @refresh="onCategoryChange"
        />
      </el-tab-pane>
      <el-tab-pane label="收入分类" name="收入">
        <CategoryManager
          type="income"
          :refresh-flag="props.refreshFlag"
          @refresh="onCategoryChange"
        />
      </el-tab-pane>
    </el-tabs>
  </el-card>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
const emit = defineEmits(['refresh'])
const props = defineProps({ refreshFlag: Number })
import api from '@/api'
import CategoryManager from './CategoryManager.vue'

const selectedMonth = ref(new Date().toISOString().slice(0, 7))
const budgets = ref([])
const expenseCategories = ref([])
const activeTab = ref('支出')

const budgetForm = ref({
  category: '',
  amount: 0
})

async function fetchBudgets() {
  const month = selectedMonth.value
  const [bRes, cRes] = await Promise.all([
    api.get('/api/budgets', { params: { month } }),
    api.get('/api/categories', { params: { type: 'expense' } })
  ])
  budgets.value = bRes.data
  expenseCategories.value = cRes.data.map(c => c.name)
}

async function submitBudget() {
  await api.post('/api/budgets', {
    category: budgetForm.value.category,
    amount: budgetForm.value.amount,
    month: selectedMonth.value
  })
  await fetchBudgets()
  emit('refresh')
}

function onCategoryChange() {
  fetchBudgets()
  emit('refresh')
}

onMounted(fetchBudgets)
watch(() => props.refreshFlag, fetchBudgets)
</script>

<style scoped>
.mb-2 { margin-bottom: 10px; }
.mb-3 { margin-bottom: 15px; }
.form-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
@media (max-width: 600px) {
  .form-row {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>

