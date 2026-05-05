<template>
  <div class="ledger-page">
    <div class="page-header">
      <h2 class="page-title">📒 账本管理</h2>
      <ExportMenu scope="ledger" />
    </div>

    <!-- 记录表格 Tab -->
    <div class="section-card">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="支出记录" name="expense">
          <RecordTable
            :type="'expense'"
            title="支出记录"
            :show-budget="true"
          />
        </el-tab-pane>
        <el-tab-pane label="收入记录" name="income" lazy>
          <RecordTable
            :type="'income'"
            title="收入记录"
            :show-budget="false"
          />
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 预算 + 图表 -->
    <div class="ledger-layout">
      <div class="ledger-col-left">
        <BudgetAndCategoryPanel />
      </div>
      <div class="ledger-col-right">
        <ChartPanel :refresh-flag="categoryStore.refreshCounter" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onActivated, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import RecordTable from '@/components/RecordTable.vue'
import BudgetAndCategoryPanel from '@/components/BudgetAndCategoryPanel.vue'
import ChartPanel from '@/components/ChartPanel.vue'
import ExportMenu from '@/components/ExportMenu.vue'
import { useUserStore } from '@/stores/user'
import { useCategoryStore } from '@/stores/categories'

const activeTab = ref('expense')
const router = useRouter()
const userStore = useUserStore()
const categoryStore = useCategoryStore()

// 切回账本时刷新数据（refreshCounter 变化驱动 RecordTable / ChartPanel /
// BudgetAndCategoryPanel 重拉）。但 keep-alive 下用户来回切页面会反复触发，
// 导致卡顿——10 秒内只触发一次，避免无谓的并发请求。
let _lastBumpAt = 0
function bumpThrottled() {
  const now = Date.now()
  if (now - _lastBumpAt < 10_000) return
  _lastBumpAt = now
  categoryStore.bumpRefresh()
}

onActivated(bumpThrottled)

function onVisibilityChange() {
  if (document.visibilityState === 'visible') {
    // 切回前台时浏览器网络栈 / TCP 复用层可能仍在恢复，延迟 800ms 再发请求，
    // 避免和 onActivated 同瞬触发的并发请求一起被 abort 弹"network error"。
    setTimeout(bumpThrottled, 800)
  }
}

onMounted(() => {
  if (!userStore.username) router.push('/login')
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onUnmounted(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
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
  justify-content: space-between;
  gap: 12px;
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
