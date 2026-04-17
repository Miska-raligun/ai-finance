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
          <span class="chip-label">累计回报</span>
          <span class="chip-value" :class="pnlClass">
            {{ portfolio.returns.return_pct >= 0 ? '+' : '' }}{{ portfolio.returns.return_pct.toFixed(2) }}%
          </span>
        </div>
        <div class="chip">
          <span class="chip-label">风险等级</span>
          <span class="chip-value">{{ LEVEL_LABEL[portfolio.risk_level] || '未测评' }}</span>
        </div>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="invest-tabs">
      <el-tab-pane label="组合总览" name="overview">
        <div class="invest-layout">
          <div class="col-left">
            <PortfolioPie :allocation="portfolio?.allocation" />
            <el-card v-if="portfolio && portfolio.drift?.length" class="mt">
              <template #header>⚖️ 再平衡建议</template>
              <div v-if="!portfolio.risk_level" class="hint">
                先完成风险测评，建议会更贴合你的偏好。
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
import { ref, computed, onMounted, onActivated } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { useInvestmentStore } from '@/stores/investment'
import { useUserStore } from '@/stores/user'
import PortfolioPie from '@/components/PortfolioPie.vue'
import AssetTable from '@/components/AssetTable.vue'
import GoalProgress from '@/components/GoalProgress.vue'
import RiskQuestionnaire from '@/components/RiskQuestionnaire.vue'
import AdvisorChat from '@/components/AdvisorChat.vue'

const router = useRouter()
const userStore = useUserStore()
const store = useInvestmentStore()
const { assets, goals, portfolio } = storeToRefs(store)

const activeTab = ref('overview')

const TYPE_LABEL = {
  stock: '股票', fund: '基金', bond: '债券', cash: '现金',
  crypto: '加密货币', realestate: '房地产', other: '其他',
}
const LEVEL_LABEL = {
  conservative: '保守型', balanced: '平衡型', aggressive: '激进型',
}

const pnlClass = computed(() => {
  const p = portfolio.value?.returns?.return_pct ?? 0
  return p > 0 ? 'up' : p < 0 ? 'down' : ''
})

async function refreshAll() {
  await Promise.all([store.fetchAssets(), store.fetchGoals(), store.fetchPortfolio()])
}

onMounted(() => {
  if (!userStore.username) { router.push('/login'); return }
  refreshAll()
})
onActivated(refreshAll)
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

@media (max-width: 900px) {
  .invest-layout {
    flex-direction: column;
  }
  .col-left, .col-right { flex: none; width: 100%; }
}
</style>
