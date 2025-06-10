<template>
  <el-card>
    <template #header>📚 账本管理</template>

    <!-- 上半部分：两个表格并排 -->
    <el-tabs v-model="activeTab">
      <el-tab-pane label="支出记录" name="expense">
        <RecordTable :type="'expense'" :refresh-flag="refreshFlag" title="📋 支出记录表格" :show-budget="true" />
      </el-tab-pane>
      <el-tab-pane label="收入记录" name="income">
        <RecordTable :type="'income'" :refresh-flag="refreshFlag" title="📋 收入记录表格" :show-budget="false" />
      </el-tab-pane>
    </el-tabs>

    <!-- 下半部分：左右两栏布局 -->
    <div style="display: flex; gap: 20px; margin-top: 20px">
      <!-- 左侧：预算管理和分类添加 -->
      <div style="flex: 1">
        <BudgetAndCategoryPanel @refresh="refreshFlag++" />
      </div>

      <!-- 右侧：图表分析 -->
      <div style="flex: 2">
        <ChartPanel />
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref, onActivated } from 'vue'
import RecordTable from '@/components/RecordTable.vue'
import BudgetAndCategoryPanel from '@/components/BudgetAndCategoryPanel.vue'
import ChartPanel from '@/components/ChartPanel.vue'

const activeTab = ref('expense')
const refreshFlag = ref(0)

onActivated(() => {
  refreshFlag.value++
})
</script>



