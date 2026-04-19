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

    <el-tabs v-model="activeTab" class="invest-tabs">
      <el-tab-pane label="组合总览" name="overview">
        <div class="invest-layout">
          <div class="col-left">
            <PortfolioPie :allocation="portfolio?.allocation" />
            <el-card v-if="portfolio && portfolio.drift?.length" class="mt">
              <template #header>
                <div class="rebalance-header">
                  <span>⚖️ 再平衡建议</span>
                  <el-tooltip placement="top" effect="light">
                    <template #content>
                      <div class="rebalance-tooltip">
                        <div class="tooltip-title">
                          目标配比基于你的风险等级
                          <b>{{ LEVEL_LABEL[portfolio.risk_level] || '未测评（用默认保守档）' }}</b>
                        </div>
                        <table class="tooltip-table">
                          <thead>
                            <tr><th>类型</th><th>目标占比</th></tr>
                          </thead>
                          <tbody>
                            <tr v-for="(v, k) in portfolio.target_allocation || {}" :key="k">
                              <td>{{ TYPE_LABEL[k] || k }}</td>
                              <td>{{ (v * 100).toFixed(0) }}%</td>
                            </tr>
                          </tbody>
                        </table>
                        <div class="tooltip-note">
                          drift = 当前占比 − 目标占比；|drift| &lt; 1% 建议"保持"，正值减仓、负值加仓。
                        </div>
                      </div>
                    </template>
                    <span class="help-icon" aria-label="计算说明">ℹ️</span>
                  </el-tooltip>
                </div>
              </template>
              <div v-if="!portfolio.risk_level" class="hint">
                <b>先完成风险测评</b>可得到贴合你的目标配比，否则按默认"保守"档位计算。
              </div>
              <el-table :data="portfolio.drift" size="small">
                <el-table-column label="类型">
                  <template #default="{ row }">{{ TYPE_LABEL[row.type] || row.type }}</template>
                </el-table-column>
                <el-table-column prop="current_pct" label="当前" align="right">
                  <template #default="{ row }">{{ row.current_pct.toFixed(1) }}%</template>
                </el-table-column>
                <el-table-column prop="target_pct" label="目标" align="right">
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
import { ref, computed, onMounted, onActivated, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { useInvestmentStore } from '@/stores/investment'
import { useUserStore } from '@/stores/user'
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

const activeTab = ref('overview')

const TYPE_LABEL = {
  stock: '股票', fund: '基金', bond: '债券', cash: '现金',
  crypto: '加密货币', realestate: '房地产', other: '其他',
}
const LEVEL_LABEL = {
  conservative: '保守型', balanced: '平衡型', aggressive: '激进型',
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
  await Promise.all([
    store.fetchAssets(),
    store.fetchGoals(),
    store.fetchPortfolio({ refresh: quotes }),
  ])
}

onMounted(() => {
  if (!userStore.username) { router.push('/login'); return }
  refreshAll({ quotes: true })  // 进页面时刷一次行情
})
onActivated(() => refreshAll({ quotes: true }))  // 切回 tab 也刷
watch(refreshCounter, () => refreshAll({ quotes: false }))  // 增删改后只重读数据
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
</style>
