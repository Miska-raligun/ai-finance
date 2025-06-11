<template>
  <el-card>
    <template #header>📚 账本管理</template>

    <!-- 上半部分：两个表格并排 -->
    <el-tabs v-model="activeTab">
      <el-tab-pane label="支出记录" name="expense">
        <RecordTable
          :type="'expense'"
          :refresh-flag="refreshFlag"
          title="📋 支出记录表格"
          :show-budget="true"
          @refresh="refreshFlag++"
        />
      </el-tab-pane>
      <el-tab-pane label="收入记录" name="income">
        <RecordTable
          :type="'income'"
          :refresh-flag="refreshFlag"
          title="📋 收入记录表格"
          :show-budget="false"
          @refresh="refreshFlag++"
        />
      </el-tab-pane>
    </el-tabs>

    <!-- 下半部分：左右两栏布局 -->
    <div class="ledger-layout">
      <!-- 左侧：预算管理和分类添加 -->
      <div style="flex: 1">
        <BudgetAndCategoryPanel
          :refresh-flag="refreshFlag"
          @refresh="refreshFlag++"
        />
      </div>

      <!-- 右侧：图表分析 -->
      <div style="flex: 2">
        <ChartPanel :refresh-flag="refreshFlag" />
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref, onActivated, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import RecordTable from '@/components/RecordTable.vue'
import BudgetAndCategoryPanel from '@/components/BudgetAndCategoryPanel.vue'
import ChartPanel from '@/components/ChartPanel.vue'

const activeTab = ref('expense')
const refreshFlag = ref(0)
const router = useRouter()

onActivated(() => {
  refreshFlag.value++
})

function onStorage(e) {
  if (e.key === 'record_added') {
    refreshFlag.value++
  }
}

onMounted(() => {
  const token = localStorage.getItem('token')
  if (!token) {
    router.push('/login')
  }
  window.addEventListener('storage', onStorage)
})
onBeforeUnmount(() => window.removeEventListener('storage', onStorage))
</script>

<style scoped>
.ledger-layout {
  display: flex;
  gap: 20px;
  margin-top: 20px;
  align-items: flex-start;
}

@media (max-width: 600px) {
  .ledger-layout {
    flex-direction: column;
  }
}
</style>


