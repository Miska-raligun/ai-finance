<template>
  <div class="ledger-page">
    <div class="page-header">
      <h2 class="page-title">📒 账本管理</h2>
    </div>

    <!-- 记录表格 Tab -->
    <div class="section-card">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="支出记录" name="expense">
          <RecordTable
            :type="'expense'"
            :refresh-flag="refreshFlag"
            title="支出记录"
            :show-budget="true"
            @refresh="refreshFlag++"
          />
        </el-tab-pane>
        <el-tab-pane label="收入记录" name="income" lazy>
          <RecordTable
            :type="'income'"
            :refresh-flag="refreshFlag"
            title="收入记录"
            :show-budget="false"
            @refresh="refreshFlag++"
          />
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 预算 + 图表 -->
    <div class="ledger-layout">
      <div class="ledger-col-left">
        <BudgetAndCategoryPanel
          :refresh-flag="refreshFlag"
          @refresh="refreshFlag++"
        />
      </div>
      <div class="ledger-col-right">
        <ChartPanel :refresh-flag="refreshFlag" />
      </div>
    </div>
  </div>
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

onActivated(() => { refreshFlag.value++ })

function onRecordChanged() { refreshFlag.value++ }

onMounted(() => {
  const name = localStorage.getItem('username')
  if (!name) router.push('/login')
  window.addEventListener('record_changed', onRecordChanged)
})
onBeforeUnmount(() => window.removeEventListener('record_changed', onRecordChanged))
</script>

<style scoped>
.ledger-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-header {
  display: flex;
  align-items: center;
}
.page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text);
  margin: 0;
}

/* 表格区域卡片 */
.section-card {
  background: var(--color-surface);
  border-radius: var(--radius-card);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-card);
  padding: 16px 18px;
}

/* 预算+图表 横向布局 */
.ledger-layout {
  display: flex;
  gap: 20px;
  align-items: flex-start;
}
.ledger-col-left { flex: 1; min-width: 0; }
.ledger-col-right { flex: 2; min-width: 0; }

@media (max-width: 768px) {
  .ledger-layout {
    flex-direction: column;
  }
  .ledger-col-left,
  .ledger-col-right {
    flex: none;
    width: 100%;
  }
}
</style>
