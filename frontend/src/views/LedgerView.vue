<template>
  <div class="ledger-page">
    <div class="page-header">
      <h2 class="page-title">📒 账本管理</h2>
      <ExportMenu scope="ledger" />
    </div>

    <!-- 本月成就 / 警示 banner —— 数据驱动 -->
    <transition name="badge">
      <div v-if="banner" :class="['ledger-banner', banner.level]">
        <img :src="banner.avatar" class="banner-avatar" alt="" aria-hidden="true">
        <div class="banner-body">
          <div class="banner-title">{{ banner.title }}</div>
          <div v-if="banner.detail" class="banner-detail">{{ banner.detail }}</div>
        </div>
      </div>
    </transition>

    <!-- 记录表格 Tab -->
    <div class="section-card animal-pop" :style="{ '--i': 0 }">
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
        <el-tab-pane label="定期账单" name="recurring" lazy>
          <RecurringRules />
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 预算 + 图表 -->
    <div class="ledger-layout">
      <div class="ledger-col-left animal-pop" :style="{ '--i': 1 }">
        <BudgetAndCategoryPanel />
      </div>
      <div class="ledger-col-right animal-pop" :style="{ '--i': 2 }">
        <ChartPanel :refresh-flag="categoryStore.refreshCounter" />
      </div>
    </div>

    <!-- 进阶视图：日历热力 + 收支桑基 -->
    <div class="ledger-viz-extra">
      <div class="animal-pop" :style="{ '--i': 3 }">
        <SpendCalendar :refresh-flag="categoryStore.refreshCounter" />
      </div>
      <div class="animal-pop" :style="{ '--i': 4 }">
        <IncomeSankey :refresh-flag="categoryStore.refreshCounter" />
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
import RecurringRules from '@/components/RecurringRules.vue'
import SpendCalendar from '@/components/SpendCalendar.vue'
import IncomeSankey from '@/components/IncomeSankey.vue'
import { useUserStore } from '@/stores/user'
import { useCategoryStore } from '@/stores/categories'
import api from '@/api'
import iconBeaver from '@/assets/decor/avatars/beaver.svg'
import iconShiba from '@/assets/decor/avatars/shiba.svg'
import iconFox from '@/assets/decor/avatars/fox.svg'
import iconOwl from '@/assets/decor/avatars/owl.svg'

const activeTab = ref('expense')
const router = useRouter()
const userStore = useUserStore()
const categoryStore = useCategoryStore()

// 本月成就 / 警示 banner
// 优先级：超预算 > 接近预算 > 比上月省更多 > 收支健康
// 数据源：/api/stats/comparison（本月 vs 上月）+ /api/budgets + 本月支出
const banner = ref(null)

async function computeBanner() {
  try {
    const month = new Date().toISOString().slice(0, 7)
    const [bRes, sRes, cRes] = await Promise.all([
      api.get('/api/budgets', { params: { month }, silent: true }).catch(() => null),
      api.get('/api/stats/by-category', { params: { month }, silent: true }).catch(() => null),
      api.get('/api/stats/comparison', { params: { month }, silent: true }).catch(() => null),
    ])
    const budgets = bRes?.data || []
    const spendMap = {}
    ;(sRes?.data || []).forEach(r => { if (r['类型'] === '支出') spendMap[r['名称']] = r['金额'] })

    // 找出超预算 / 接近预算的分类
    let over = null      // {category, budget, spent, pct}
    let warn = null
    for (const b of budgets) {
      const spent = spendMap[b.category] || 0
      if (!b.amount || b.amount <= 0) continue
      const pct = spent / b.amount * 100
      if (pct >= 100 && (!over || pct > over.pct)) over = { ...b, spent, pct }
      else if (pct >= 80 && pct < 100 && (!warn || pct > warn.pct)) warn = { ...b, spent, pct }
    }
    if (over) {
      banner.value = {
        level: 'over',
        avatar: iconFox,
        title: `🚨 「${over.category}」超预算了！`,
        detail: `本月预算 ¥${over.amount}，已花 ¥${over.spent.toFixed(2)}（${over.pct.toFixed(0)}%），超出 ¥${(over.spent - over.amount).toFixed(2)}`,
      }
      return
    }
    if (warn) {
      banner.value = {
        level: 'warn',
        avatar: iconBeaver,
        title: `⚠️ 「${warn.category}」已用 ${warn.pct.toFixed(0)}%`,
        detail: `本月预算 ¥${warn.amount}，已花 ¥${warn.spent.toFixed(2)}，剩 ¥${(warn.amount - warn.spent).toFixed(2)}`,
      }
      return
    }

    // 没有警示 → 看是否比上月省得多
    const expense = cRes?.data?.expense
    if (expense && expense.previous > 0 && expense.change < -50) {
      const savedPct = Math.abs(expense.change_pct).toFixed(0)
      banner.value = {
        level: 'good',
        avatar: iconShiba,
        title: `🎉 本月支出比上月省了 ${savedPct}%`,
        detail: `已支出 ¥${expense.current.toFixed(2)}（上月 ¥${expense.previous.toFixed(2)}），继续保持～`,
      }
      return
    }

    // 收支健康提示（只在数据存在时）
    const balance = cRes?.data?.balance
    if (balance && balance.current > 0) {
      banner.value = {
        level: 'info',
        avatar: iconOwl,
        title: `🌱 本月净结余 +¥${balance.current.toFixed(2)}`,
        detail: '收支健康，记得按时设置预算 / 调整目标。',
      }
      return
    }
    banner.value = null
  } catch {
    banner.value = null
  }
}

// 切回账本时刷新数据（refreshCounter 变化驱动 RecordTable / ChartPanel /
// BudgetAndCategoryPanel 重拉）。但 keep-alive 下用户来回切页面会反复触发，
// 导致卡顿——10 秒内只触发一次，避免无谓的并发请求。
let _lastBumpAt = 0
function bumpThrottled() {
  const now = Date.now()
  if (now - _lastBumpAt < 10_000) return
  _lastBumpAt = now
  categoryStore.bumpRefresh()
  computeBanner()  // 数据可能变了，刷新成就 / 警示
}

onActivated(() => {
  bumpThrottled()
  // 首次激活也算
  if (!banner.value) computeBanner()
})

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
  computeBanner()
})

onUnmounted(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<style scoped>
/* 本月成就 / 警示 banner */
.ledger-banner {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 18px;
  border-radius: 16px;
  border: 2px solid transparent;
  box-shadow: 0 3px 0 0 var(--shadow-anchor-light);
  font-family: inherit;
}
.ledger-banner.over {
  background: #fde4e4;
  border-color: var(--color-error);
  color: var(--color-error-active);
  animation: banner-pulse 1.6s ease-in-out infinite;
}
.ledger-banner.warn {
  background: #fef3c7;
  border-color: var(--color-warning);
  color: #92580d;
}
.ledger-banner.good {
  background: #e8f5d8;
  border-color: var(--color-success);
  color: var(--color-success-active);
}
.ledger-banner.info {
  background: var(--color-primary-light);
  border-color: var(--color-primary);
  color: var(--color-primary-dark);
}
@keyframes banner-pulse {
  0%, 100% { box-shadow: 0 3px 0 0 var(--shadow-anchor-light); }
  50%      { box-shadow: 0 3px 0 0 var(--shadow-anchor-light), 0 0 0 4px rgba(224, 90, 90, 0.18); }
}
.banner-avatar {
  width: 42px;
  height: 42px;
  background: rgba(255,255,255,0.7);
  border-radius: 50%;
  padding: 2px;
  flex-shrink: 0;
}
.banner-body { flex: 1; min-width: 0; }
.banner-title {
  font-weight: 800;
  font-size: 14px;
  letter-spacing: 0.02em;
}
.banner-detail {
  font-size: 12px;
  color: var(--color-text);
  opacity: 0.85;
  margin-top: 2px;
}

/* banner transition */
.badge-enter-active { animation: badge-pop 0.45s cubic-bezier(0.25, 1.2, 0.4, 1); }
.badge-leave-active { animation: badge-pop 0.2s reverse ease-out; }
@keyframes badge-pop {
  0% { opacity: 0; transform: scale(0.9) translateY(-6px); }
  100% { opacity: 1; transform: none; }
}

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

/* 进阶视图：日历热力 + 桑基图，桌面端两列，移动端纵向 */
.ledger-viz-extra {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}
@media (max-width: 900px) {
  .ledger-viz-extra { grid-template-columns: 1fr; }
}

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
