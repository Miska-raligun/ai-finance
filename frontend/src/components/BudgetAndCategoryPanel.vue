<template>
  <el-card>
    <template #header>预算 &amp; 分类管理</template>

    <!-- 月份选择 -->
    <div class="section-label">选择月份</div>
    <el-date-picker
      v-model="selectedMonth"
      type="month"
      value-format="YYYY-MM"
      placeholder="选择月份"
      @change="fetchBudgets"
      style="width: 100%; margin-bottom: 14px;"
    />

    <!-- 预算表 -->
    <el-table :data="budgets" size="small" class="budget-table" style="width: 100%">
      <el-table-column prop="category" label="分类" />
      <el-table-column prop="amount" label="预算额">
        <template #default="scope">
          <span class="amount-text">¥{{ scope.row.amount }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remaining" label="剩余预算">
        <template #default="scope">
          <span :class="scope.row.remaining < 0 ? 'amount-expense' : 'amount-income'">
            ¥{{ scope.row.remaining }}
          </span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 添加/更新预算 -->
    <div class="budget-form">
      <div class="section-label" style="margin-top: 14px;">设置预算</div>
      <div class="budget-inputs">
        <el-select v-model="budgetForm.category" placeholder="选择分类" style="flex: 1">
          <el-option v-for="cat in expenseCategories" :key="cat" :label="cat" :value="cat" />
        </el-select>
        <el-input-number v-model="budgetForm.amount" :min="0" style="flex: 1; min-width: 100px;" />
        <el-button type="primary" size="small" @click="submitBudget">确定</el-button>
      </div>
    </div>

    <el-divider style="margin: 16px 0;" />

    <!-- 分类管理 -->
    <el-tabs v-model="activeTab">
      <el-tab-pane label="支出分类" name="支出">
        <CategoryManager type="expense" :refresh-flag="props.refreshFlag" @refresh="onCategoryChange" />
      </el-tab-pane>
      <el-tab-pane label="收入分类" name="收入">
        <CategoryManager type="income" :refresh-flag="props.refreshFlag" @refresh="onCategoryChange" />
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
const budgetForm = ref({ category: '', amount: 0 })

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
.section-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}

.budget-table :deep(th.el-table__cell) {
  background: #F8FAFC !important;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 600;
}

.amount-text { font-weight: 500; color: var(--color-text); }
.amount-expense { color: #ef4444; font-weight: 600; }
.amount-income  { color: #22c55e; font-weight: 600; }

.budget-inputs {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .budget-inputs {
    flex-direction: column;
    align-items: stretch;
  }
  .budget-inputs .el-button {
    width: 100%;
  }
  .budget-inputs :deep(.el-input-number) {
    width: 100% !important;
  }
}
</style>
