<template>
  <div class="invest-page">
    <div class="page-header">
      <h2 class="page-title">📈 投资理财</h2>
      <div v-if="portfolio" class="summary-chips">
        <div class="chip">
          <span class="chip-label">总市值</span>
          <span class="chip-value">¥{{ portfolio.total_value.toFixed(2) }}</span>
        </div>
        <div class="chip">
          <span class="chip-label">累计盈亏</span>
          <span class="chip-value" :class="pnlClass">
            {{ pnlSign }}¥{{ Math.abs(portfolio.returns.pnl || 0).toFixed(2) }}
          </span>
        </div>
        <div class="chip">
          <span class="chip-label">回报率</span>
          <span class="chip-value" :class="pnlClass">
            {{ pnlSign }}{{ Math.abs(portfolio.returns.return_pct || 0).toFixed(2) }}%
          </span>
        </div>
        <div class="chip">
          <span class="chip-label">风险等级</span>
          <span class="chip-value">{{ LEVEL_LABEL[portfolio.risk_level] || '未测评' }}</span>
        </div>
      </div>
      <ExportMenu scope="investment" />
    </div>

    <el-alert
      v-if="showOnboarding"
      :closable="false"
      type="info"
      class="invest-onboarding"
    >
      <template #title>
        <b>🎯 先在「资产明细」里设置类型</b>
      </template>
      还没有资产类型也没有持仓。去「资产明细」tab 点「⚙️ 类型管理」，按你自己的习惯创建几种类型（例如 A股 / 基金 / 活期存款），再开始录入资产。
      <div class="onboarding-actions">
        <el-button size="small" type="primary" @click="activeTab = 'assets'">去资产明细</el-button>
      </div>
    </el-alert>

    <el-tabs v-model="activeTab" class="invest-tabs">
      <el-tab-pane label="组合总览" name="overview">
        <div class="invest-layout">
          <div class="col-left">
            <PortfolioPie :allocation="portfolio?.allocation" />
            <el-card v-if="portfolio && portfolio.allocation?.by_type?.length" class="mt">
              <template #header>
                <div class="rebalance-header">
                  <span>⚖️ 再平衡建议</span>
                  <div class="rebalance-header-right">
                    <span v-if="rebalance?.cached_at" class="cached-hint">
                      {{ rebalanceSourceLabel }} · {{ formatCached(rebalance.cached_at) }}
                    </span>
                    <el-button size="small" :loading="rebalanceLoading" @click="requestRebalance(false)">
                      {{ rebalance?.targets && Object.keys(rebalance.targets).length ? '🔄 刷新' : '🤖 让 AI 分析' }}
                    </el-button>
                    <el-button
                      v-if="rebalance?.targets && Object.keys(rebalance.targets).length"
                      size="small" plain
                      :loading="rebalanceLoading"
                      @click="requestRebalance(true)"
                    >重新分析</el-button>
                  </div>
                </div>
              </template>

              <div v-if="!rebalance" class="rebalance-empty">
                点右上角「让 AI 分析」生成当前持仓对应的目标配比。
              </div>
              <template v-else-if="rebalance.drift?.length">
                <div v-if="rebalance.rationale" class="rebalance-rationale">
                  💡 {{ rebalance.rationale }}
                </div>

                <!-- 桌面：5 列表格信息密度高 -->
                <el-table v-if="!isMobile" :data="rebalance.drift" size="small">
                  <el-table-column label="类型">
                    <template #default="{ row }">{{ row.type }}</template>
                  </el-table-column>
                  <el-table-column prop="current_pct" label="当前" align="right">
                    <template #default="{ row }">{{ row.current_pct.toFixed(1) }}%</template>
                  </el-table-column>
                  <el-table-column prop="target_pct" label="AI 建议" align="right">
                    <template #default="{ row }">{{ row.target_pct.toFixed(1) }}%</template>
                  </el-table-column>
                  <el-table-column prop="drift_pct" label="漂移" align="right">
                    <template #default="{ row }">
                      <span :class="row.drift_pct > 0 ? 'up' : row.drift_pct < 0 ? 'down' : ''">
                        {{ row.drift_pct > 0 ? '+' : '' }}{{ row.drift_pct.toFixed(1) }}%
                      </span>
                    </template>
                  </el-table-column>
                  <el-table-column prop="action" label="动作" />
                </el-table>

                <!-- 移动端：卡片化避免 5 列硬塞 -->
                <div v-else class="rebalance-mobile-list">
                  <div v-for="row in rebalance.drift" :key="row.type" class="rb-card">
                    <div class="rb-card-head">
                      <span class="rb-type">{{ row.type }}</span>
                      <span
                        class="rb-drift"
                        :class="row.drift_pct > 0 ? 'up' : row.drift_pct < 0 ? 'down' : ''"
                      >{{ row.drift_pct > 0 ? '+' : '' }}{{ row.drift_pct.toFixed(1) }}%</span>
                    </div>
                    <div class="rb-card-body">
                      <span class="rb-pct">当前 {{ row.current_pct.toFixed(1) }}%</span>
                      <span class="rb-arrow">→</span>
                      <span class="rb-pct rb-target">AI {{ row.target_pct.toFixed(1) }}%</span>
                    </div>
                    <div class="rb-card-action">{{ row.action }}</div>
                  </div>
                </div>
              </template>
              <el-empty v-else :description="rebalance.rationale || '暂无可执行建议'" :image-size="60" />
            </el-card>
          </div>
          <div class="col-right">
            <AdvisorChat />
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="资产明细" name="assets" lazy>
        <AssetTable :assets="assets" />
      </el-tab-pane>

      <el-tab-pane label="理财目标" name="goals" lazy>
        <GoalProgress :goals="goals" />
      </el-tab-pane>

      <el-tab-pane label="风险测评" name="risk" lazy>
        <RiskQuestionnaire />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onActivated, onBeforeUnmount, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { useInvestmentStore } from '@/stores/investment'
import { useUserStore } from '@/stores/user'
import { useAssetTypesStore } from '@/stores/assetTypes'
import PortfolioPie from '@/components/PortfolioPie.vue'
import AssetTable from '@/components/AssetTable.vue'
import GoalProgress from '@/components/GoalProgress.vue'
import RiskQuestionnaire from '@/components/RiskQuestionnaire.vue'
import AdvisorChat from '@/components/AdvisorChat.vue'
import ExportMenu from '@/components/ExportMenu.vue'

const router = useRouter()
const userStore = useUserStore()
const store = useInvestmentStore()
const { assets, goals, portfolio, refreshCounter } = storeToRefs(store)
const typesStore = useAssetTypesStore()
const { types: assetTypes } = storeToRefs(typesStore)

const showOnboarding = computed(() =>
  assetTypes.value.length === 0 && assets.value.length === 0,
)

const activeTab = ref('overview')

// 768px 以下切到移动端布局：再平衡表 / 顶部 chips 改卡片化与 2×2 网格
const _mq = window.matchMedia('(max-width: 768px)')
const isMobile = ref(_mq.matches)
function _onMq(e) { isMobile.value = e.matches }
onMounted(() => _mq.addEventListener('change', _onMq))
onBeforeUnmount(() => _mq.removeEventListener('change', _onMq))

const LEVEL_LABEL = {
  conservative: '保守型', balanced: '平衡型', aggressive: '激进型',
}

const rebalance = ref(null)
const rebalanceLoading = ref(false)

const rebalanceSourceLabel = computed(() => {
  if (!rebalance.value) return ''
  return rebalance.value.source === 'llm' ? 'AI 刚出的建议' : '缓存结果'
})

function formatCached(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  return sameDay
    ? `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
    : `${d.getMonth() + 1}/${d.getDate()}`
}

async function requestRebalance(force) {
  rebalanceLoading.value = true
  try {
    rebalance.value = await store.fetchRebalance({
      force,
      llm: userStore.llmPayload,
    })
  } catch (e) {
    rebalance.value = { targets: {}, drift: [], rationale: e?.response?.data?.error || '调用失败' }
  } finally {
    rebalanceLoading.value = false
  }
}

const pnlClass = computed(() => {
  const p = portfolio.value?.returns?.pnl ?? 0
  return p > 0 ? 'up' : p < 0 ? 'down' : ''
})
const pnlSign = computed(() => {
  const p = portfolio.value?.returns?.pnl ?? 0
  if (p > 0) return '+'
  if (p < 0) return '−'
  return ''
})

async function refreshAll({ quotes = false } = {}) {
  typesStore.fetchTypes()  // 异步启动，不阻塞下面
  // quotes=true 时，后端在 portfolio 接口里会把最新行情写回 assets 表，
  // 必须先等它完成再拉 assets，否则表格读到的是旧值。
  if (quotes) {
    await store.fetchPortfolio({ refresh: true })
    await Promise.all([store.fetchAssets(), store.fetchGoals()])
  } else {
    await Promise.all([
      store.fetchAssets(),
      store.fetchGoals(),
      store.fetchPortfolio({ refresh: false }),
    ])
  }
}

onMounted(() => {
  if (!userStore.username) { router.push('/login'); return }
  refreshAll({ quotes: true })  // 进页面时刷一次行情
})
onActivated(() => refreshAll({ quotes: true }))  // 切回 tab 也刷
watch(refreshCounter, () => {
  refreshAll({ quotes: false })
  rebalance.value = null  // 组合变了，旧的再平衡分析作废
})
</script>

<style scoped>
.invest-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text);
  margin: 0;
}
.summary-chips {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.chip {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  padding: 8px 14px;
  box-shadow: var(--shadow-card);
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
}
.chip-label { color: var(--color-text-muted); }
.chip-value {
  font-weight: 700;
  color: var(--color-primary);
  font-variant-numeric: tabular-nums;
}
.invest-onboarding {
  margin-bottom: 12px;
}
.onboarding-actions {
  margin-top: 8px;
}
.invest-tabs {
  background: var(--color-surface);
  border-radius: var(--radius-card);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-card);
  padding: 6px 18px 18px;
}
.invest-layout {
  display: flex;
  gap: 20px;
  align-items: flex-start;
  margin-top: 8px;
}
.col-left { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 16px; }
.col-right { flex: 1.4; min-width: 0; }
.mt { margin-top: 0; }
.hint {
  padding: 8px 12px;
  margin-bottom: 10px;
  background: #FFF7ED;
  color: #9A3412;
  border-radius: 8px;
  font-size: 12px;
}
.up { color: #EF4444; font-weight: 600; }
.down { color: #22C55E; font-weight: 600; }

.rebalance-header {
  display: flex; align-items: center; gap: 8px;
  justify-content: space-between; width: 100%;
}
.rebalance-header-right {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.cached-hint {
  font-size: 11px; color: var(--color-text-muted);
}
.rebalance-empty {
  padding: 18px 8px; color: var(--color-text-muted);
  font-size: 13px; text-align: center;
}
.rebalance-rationale {
  background: #F0F7FF; color: var(--color-primary);
  padding: 8px 12px; border-radius: 8px;
  font-size: 12px; margin-bottom: 10px; line-height: 1.6;
}
.help-icon {
  cursor: help;
  font-size: 14px;
  opacity: 0.7;
}
.help-icon:hover { opacity: 1; }
:deep(.el-popper) .rebalance-tooltip { max-width: 280px; }
.rebalance-tooltip .tooltip-title { font-size: 13px; margin-bottom: 8px; }
.rebalance-tooltip .tooltip-table {
  border-collapse: collapse; width: 100%; margin: 6px 0; font-size: 12px;
}
.rebalance-tooltip .tooltip-table th,
.rebalance-tooltip .tooltip-table td {
  border: 1px solid var(--color-border); padding: 3px 8px;
}
.rebalance-tooltip .tooltip-note {
  font-size: 11px; color: var(--color-text-muted); margin-top: 6px; line-height: 1.5;
}

@media (max-width: 900px) {
  .invest-layout {
    flex-direction: column;
  }
  .col-left, .col-right { flex: none; width: 100%; }
}

/* 移动端：summary chips 改 2×2 网格，避免 4 个 chip 错落换行；
   chip 内部 label / value 改纵向排列让数字更醒目。 */
@media (max-width: 768px) {
  .page-header { gap: 10px; }
  .page-title { font-size: 18px; }
  .summary-chips {
    width: 100%;
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }
  .chip {
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
    padding: 8px 12px;
  }
  .chip-label { font-size: 11px; }
  .chip-value { font-size: 14px; }

  /* 再平衡 header 在窄屏纵向排：标题独占，按钮组下方 */
  .rebalance-header {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }
  .rebalance-header-right {
    justify-content: flex-end;
    flex-wrap: wrap;
  }
  .cached-hint { order: -1; flex-basis: 100%; }

  /* 紧凑 tabs */
  .invest-tabs { padding: 4px 12px 14px; }
}

/* 再平衡建议 移动端卡片列表 */
.rebalance-mobile-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rb-card {
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: 10px 12px;
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.rb-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.rb-type {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
}
.rb-drift {
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.rb-card-body {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}
.rb-target { color: var(--color-primary); font-weight: 600; }
.rb-arrow { color: var(--color-text-muted); }
.rb-card-action {
  font-size: 12px;
  color: var(--color-text-muted);
  background: var(--color-bg);
  padding: 4px 8px;
  border-radius: 6px;
  align-self: flex-start;
}
</style>
