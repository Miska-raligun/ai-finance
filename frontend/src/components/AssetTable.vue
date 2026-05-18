<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <span class="header-title">📁 我的资产</span>
        <div class="header-actions">
          <el-select
            v-model="filterType"
            size="small"
            class="type-filter"
            placeholder="全部类型"
          >
            <el-option label="全部类型" value="" />
            <el-option v-for="t in assetTypes" :key="t.name" :value="t.name" :label="t.name" />
          </el-select>
          <div class="header-buttons">
            <el-button size="small" class="header-btn" @click="showTypeManager = true">
              <span class="btn-emoji">⚙️</span><span class="btn-label">类型管理</span>
            </el-button>
            <el-button size="small" class="header-btn" :loading="refreshing" @click="refreshPrices">
              <span class="btn-emoji">🔄</span><span class="btn-label">刷新行情</span>
            </el-button>
            <el-button size="small" class="header-btn" type="primary" @click="openCreate">
              <span class="btn-emoji">＋</span><span class="btn-label">新增资产</span>
            </el-button>
          </div>
        </div>
      </div>
    </template>

    <!-- 桌面：信息密度高的表格 -->
    <el-table
      v-if="!isMobile"
      :data="displayedAssets"
      size="small"
      empty-text="还没有符合条件的资产"
      style="width: 100%"
      :default-sort="{ prop: 'current_value', order: 'descending' }"
      @row-click="handleRowClick"
      :row-class-name="isTouch ? 'touch-tappable-row' : ''"
    >
      <el-table-column prop="name" label="名称" min-width="120" sortable />
      <el-table-column prop="type" label="类型" width="100" sortable>
        <template #default="{ row }">{{ row.type }}</template>
      </el-table-column>
      <el-table-column prop="symbol" label="代码" width="110" sortable>
        <template #default="{ row }">{{ row.symbol || '—' }}</template>
      </el-table-column>
      <el-table-column prop="holdings" label="数量" width="100" align="right" sortable>
        <template #default="{ row }">{{ schemaOf(row.type).showHoldings ? (row.holdings || '—') : '—' }}</template>
      </el-table-column>
      <el-table-column
        label="成本单价" width="110" align="right"
        sortable :sort-method="sortByUnitCost"
      >
        <template #default="{ row }">
          <span v-if="unitCostStr(row) !== '—'">¥{{ unitCostStr(row) }}</span>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column prop="cost_basis" label="总成本" width="110" align="right" sortable>
        <template #default="{ row }">
          <span v-if="schemaOf(row.type).hasCost">¥{{ (row.cost_basis || 0).toFixed(2) }}</span>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column prop="current_value" label="现值" width="130" align="right" sortable>
        <template #default="{ row }">
          <div class="value-cell">
            <span>¥{{ (row.current_value || 0).toFixed(2) }}</span>
            <el-tag
              v-if="isAutoPriced(row)"
              size="small"
              type="success"
              effect="plain"
              class="auto-tag"
            >自动</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="盈亏" width="130" align="right" sortable :sort-method="sortByPnl">
        <template #default="{ row }">
          <span :class="pnlClass(row)">{{ pnlStr(row) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 移动端：卡片列表，避免 8 列硬塞造成横向溢出 / 文字挤压 -->
    <div v-else class="mobile-asset-list">
      <div
        v-for="(row, idx) in sortedMobileAssets"
        :key="row.id"
        class="mobile-asset-card animal-pop"
        :style="{ '--i': Math.min(idx, 8) }"
        @click="handleRowClick(row, null, $event)"
      >
        <div class="mobile-card-row mobile-card-head">
          <div class="mobile-card-title">
            <span class="mobile-asset-name">{{ row.name }}</span>
            <el-tag size="small" effect="plain" class="mobile-type-tag">{{ row.type }}</el-tag>
          </div>
          <div class="mobile-card-pnl" :class="pnlClass(row)">
            {{ pnlStr(row) }}
          </div>
        </div>

        <div class="mobile-card-row">
          <span class="mobile-card-label">现值</span>
          <span class="mobile-card-value">
            ¥{{ (row.current_value || 0).toFixed(2) }}
            <el-tag
              v-if="isAutoPriced(row)"
              size="small"
              type="success"
              effect="plain"
              class="auto-tag"
            >自动</el-tag>
          </span>
        </div>

        <div v-if="schemaOf(row.type).showHoldings || schemaOf(row.type).showSymbol" class="mobile-card-row mobile-card-meta">
          <template v-if="schemaOf(row.type).showSymbol && row.symbol">
            <span class="mobile-meta-pill">{{ row.symbol }}</span>
          </template>
          <template v-if="schemaOf(row.type).showHoldings && row.holdings">
            <span class="mobile-meta-pill">持仓 {{ row.holdings }}</span>
          </template>
          <template v-if="schemaOf(row.type).showUnitCost && unitCostStr(row) !== '—'">
            <span class="mobile-meta-pill">成本 ¥{{ unitCostStr(row) }}</span>
          </template>
        </div>
      </div>
      <div v-if="!sortedMobileAssets.length" class="mobile-empty">还没有符合条件的资产</div>
    </div>

    <!-- 行详情 / 编辑抽屉，和账本记录一致的 view + edit 双模式 -->
    <el-drawer
      v-model="showDrawer"
      direction="btt"
      :with-header="false"
      :size="drawerMode === 'edit' ? '540px' : '400px'"
      class="asset-drawer"
      append-to-body
      @close="onDrawerClose"
    >
      <div class="drawer-handle-bar"></div>

      <!-- VIEW 模式：只展示该类型相关字段 -->
      <template v-if="drawerMode === 'view' && popoverRow">
        <div class="drawer-body">
          <div class="drawer-row">
            <span class="drawer-label">名称</span>
            <span class="drawer-value">{{ popoverRow.name }}</span>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">类型</span>
            <span class="drawer-value">{{ popoverRow.type }}</span>
          </div>
          <div v-if="schemaOf(popoverRow.type).showSymbol" class="drawer-row">
            <span class="drawer-label">代码</span>
            <span class="drawer-value text-normal">{{ popoverRow.symbol || '—' }}</span>
          </div>
          <div v-if="schemaOf(popoverRow.type).showHoldings" class="drawer-row">
            <span class="drawer-label">持仓</span>
            <span class="drawer-value text-normal">{{ popoverRow.holdings || '—' }}</span>
          </div>
          <div v-if="schemaOf(popoverRow.type).showUnitCost && popoverRow.holdings > 0" class="drawer-row">
            <span class="drawer-label">成本价</span>
            <span class="drawer-value">¥{{ unitCostStr(popoverRow) }}</span>
          </div>
          <div v-if="schemaOf(popoverRow.type).hasCost" class="drawer-row">
            <span class="drawer-label">总成本</span>
            <span class="drawer-value">¥{{ (popoverRow.cost_basis || 0).toFixed(2) }}</span>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">{{ valueLabel(popoverRow.type) }}</span>
            <span class="drawer-value">
              ¥{{ (popoverRow.current_value || 0).toFixed(2) }}
              <el-tag
                v-if="isAutoPriced(popoverRow)"
                size="small"
                type="success"
                effect="plain"
                class="auto-tag"
              >自动</el-tag>
            </span>
          </div>
          <div v-if="schemaOf(popoverRow.type).hasCost" class="drawer-row">
            <span class="drawer-label">盈亏</span>
            <span class="drawer-value" :class="pnlClass(popoverRow)">{{ pnlStr(popoverRow) }}</span>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">备注</span>
            <span class="drawer-value text-normal">{{ popoverRow.notes || '—' }}</span>
          </div>
          <div v-if="popoverRow.updated_at" class="drawer-row">
            <span class="drawer-label">更新于</span>
            <span class="drawer-value text-muted">{{ formatTime(popoverRow.updated_at) }}</span>
          </div>

          <!-- 市值历史折线（仅 hasCost && holdings>0 时显示） -->
          <div v-if="canShowHistory(popoverRow)" class="asset-history">
            <div class="asset-history-head">
              <span class="asset-history-title">📉 市值走势</span>
              <el-radio-group v-model="historyDays" size="small" @change="loadHistory(popoverRow)">
                <el-radio-button :value="7">7天</el-radio-button>
                <el-radio-button :value="30">30天</el-radio-button>
                <el-radio-button :value="90">90天</el-radio-button>
              </el-radio-group>
            </div>
            <div v-if="historyLoading" class="asset-history-loading">加载中...</div>
            <div v-else-if="!historyPoints.length" class="asset-history-empty">
              还没记录到走势 — 试试刷新行情或修改一下市值，会自动写入一条快照。
            </div>
            <template v-else>
              <canvas ref="historyChartRef" class="asset-history-chart"></canvas>
              <div v-if="historyPoints.length < 3" class="asset-history-note">
                目前只有 {{ historyPoints.length }} 个数据点；多更新几次行情后曲线会更顺滑。
              </div>
            </template>
          </div>
        </div>
        <div class="drawer-footer drawer-footer-actions">
          <el-button class="drawer-action-btn" plain type="danger" @click="deleteFromDrawer">
            🗑️ 删除
          </el-button>
          <el-button
            v-if="canSell(popoverRow)"
            class="drawer-action-btn"
            plain
            @click="openSellDialog"
          >💰 卖出</el-button>
          <el-button class="drawer-action-btn" plain @click="archiveFromDrawer">
            📦 归档
          </el-button>
          <el-button class="drawer-action-btn" type="primary" @click="startDrawerEdit">
            ✏️ 编辑
          </el-button>
        </div>
      </template>

      <!-- EDIT 模式：按类型决定要展示的字段 -->
      <template v-if="drawerMode === 'edit' && editingRow">
        <div class="drawer-edit-title">{{ editingRow.id ? '编辑资产' : '新增资产' }}</div>
        <div class="drawer-edit-form">
          <div class="drawer-edit-field">
            <label class="drawer-edit-label">名称</label>
            <el-input v-model="editingRow.name" :placeholder="namePlaceholder(editingRow.type)" />
          </div>
          <div class="drawer-edit-field">
            <label class="drawer-edit-label">
              类型
              <span v-if="!assetTypes.length" class="required-hint">
                （还没有类型，请先点右上角「⚙️ 类型管理」创建一个）
              </span>
            </label>
            <el-select
              v-model="editingRow.type"
              style="width:100%"
              placeholder="选择类型"
              :no-data-text="'暂无类型，去类型管理创建'"
            >
              <el-option
                v-for="t in assetTypes"
                :key="t.name"
                :value="t.name"
                :label="t.name"
              />
            </el-select>
            <div class="type-hint">{{ typeHint(editingRow.type) }}</div>
          </div>

          <div v-if="editingSchema.showSymbol" class="drawer-edit-field">
            <label class="drawer-edit-label">
              代码
              <span v-if="editingSchema.autoQuote" class="required-hint">（建议填写，用于自动同步市值）</span>
            </label>
            <el-input
              v-model="editingRow.symbol"
              :placeholder="symbolPlaceholder(editingRow.type)"
            />
          </div>

          <div v-if="editingSchema.showHoldings" class="drawer-edit-field">
            <label class="drawer-edit-label">持仓数量</label>
            <el-input-number
              v-model="editingRow.holdings"
              :min="0"
              :step="1"
              controls-position="right"
              style="width:100%"
            />
          </div>

          <div v-if="editingSchema.showUnitCost" class="drawer-edit-field">
            <label class="drawer-edit-label">成本价（每股/每份）</label>
            <el-input-number
              v-model="editingRow.cost_price"
              :min="0"
              :step="0.01"
              :precision="4"
              controls-position="right"
              style="width:100%"
            />
            <div class="auto-value-hint">
              总成本 = 持仓 × 成本价 = ¥{{ computedCostBasis.toFixed(2) }}
            </div>
          </div>

          <div v-else-if="editingSchema.hasCost" class="drawer-edit-field">
            <label class="drawer-edit-label">{{ costLabel(editingRow.type) }}</label>
            <el-input-number
              v-model="editingRow.cost_basis"
              :min="0"
              :step="100"
              controls-position="right"
              style="width:100%"
            />
          </div>

          <div class="drawer-edit-field">
            <label class="drawer-edit-label">
              {{ valueLabel(editingRow.type) }}
              <span v-if="editingSchema.autoQuote" class="required-hint">
                （按行情源自动同步，无需填写）
              </span>
            </label>
            <el-input-number
              v-if="!editingSchema.autoQuote"
              v-model="editingRow.current_value"
              :min="0"
              :step="100"
              controls-position="right"
              style="width:100%"
            />
            <div v-else class="auto-value-hint">
              保存后按代码自动拉取行情并换算 = 持仓 × 最新价
            </div>
          </div>

          <div class="drawer-edit-field">
            <label class="drawer-edit-label">备注</label>
            <el-input v-model="editingRow.notes" type="textarea" :rows="2" />
          </div>
        </div>
        <div class="drawer-footer">
          <el-button class="drawer-action-btn" plain @click="cancelEdit">取消</el-button>
          <el-button class="drawer-action-btn" type="primary" @click="saveDrawerEdit">保存</el-button>
        </div>
      </template>
    </el-drawer>

    <!-- 类型管理抽屉 -->
    <el-drawer
      v-model="showTypeManager"
      direction="btt"
      :with-header="false"
      size="420px"
      class="asset-drawer"
      append-to-body
    >
      <div class="drawer-handle-bar"></div>
      <div class="drawer-edit-title">⚙️ 资产类型管理</div>
      <div class="drawer-edit-form">
        <AssetTypeManager />
      </div>
      <div class="drawer-footer">
        <el-button class="drawer-action-btn" type="primary" @click="showTypeManager = false">
          完成
        </el-button>
      </div>
    </el-drawer>

    <!-- 卖出对话框 -->
    <el-dialog
      v-model="showSellDialog"
      title="💰 卖出资产"
      width="420px"
      :close-on-click-modal="false"
      append-to-body
    >
      <div v-if="sellTarget" class="sell-form">
        <div class="sell-info">
          <div><strong>{{ sellTarget.name }}</strong>（{{ sellTarget.type }}）</div>
          <div class="sell-info-line">
            当前持仓 {{ sellTarget.holdings }}，
            成本单价 ¥{{ sellUnitCost.toFixed(4) }}，
            最新市价
            <template v-if="sellLatestPrice > 0">¥{{ sellLatestPrice.toFixed(4) }}</template>
            <template v-else>—</template>
          </div>
        </div>
        <el-form label-width="84px" size="default">
          <el-form-item label="卖出价">
            <el-input-number
              v-model="sellForm.price"
              :min="0"
              :step="0.01"
              :precision="4"
              controls-position="right"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="数量">
            <el-input-number
              v-model="sellForm.quantity"
              :min="0"
              :max="sellTarget.holdings"
              :step="1"
              :precision="4"
              controls-position="right"
              style="width: 100%"
            />
            <div class="form-hint">
              留空或填 0 = 全部卖出（{{ sellTarget.holdings }}）
            </div>
          </el-form-item>
          <el-form-item label="手续费">
            <el-input-number
              v-model="sellForm.fee"
              :min="0"
              :step="0.01"
              :precision="2"
              controls-position="right"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="日期">
            <el-date-picker
              v-model="sellForm.date"
              type="date"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="sellForm.note" type="textarea" :rows="2" placeholder="可选" />
          </el-form-item>
        </el-form>
        <div class="sell-preview" v-if="sellPreview">
          <div class="sell-preview-row">
            <span>预计回款</span><span>¥{{ sellPreview.proceeds.toFixed(2) }}</span>
          </div>
          <div class="sell-preview-row">
            <span>摊销成本</span><span>¥{{ sellPreview.cost.toFixed(2) }}</span>
          </div>
          <div class="sell-preview-row" :class="sellPreview.pnl >= 0 ? 'pnl-up' : 'pnl-down'">
            <span>盈亏 → {{ sellPreview.pnl >= 0 ? '收入「投资盈利」' : '支出「投资亏损」' }}</span>
            <span>{{ sellPreview.pnl >= 0 ? '+' : '' }}{{ sellPreview.pnl.toFixed(2) }}</span>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="showSellDialog = false">取消</el-button>
        <el-button type="primary" :loading="selling" @click="confirmSell">
          确认卖出
        </el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { storeToRefs } from 'pinia'
import { useInvestmentStore } from '@/stores/investment'
import { useAssetTypesStore } from '@/stores/assetTypes'
import AssetTypeManager from '@/components/AssetTypeManager.vue'
import Chart from 'chart.js/auto'
import api from '@/api'

const props = defineProps({ assets: { type: Array, default: () => [] } })
const store = useInvestmentStore()
const { refreshCounter } = storeToRefs(store)

const typesStore = useAssetTypesStore()
const { types: assetTypes } = storeToRefs(typesStore)

function schemaOf(type) { return typesStore.schemaOf(type) }
function shapeOf(type) { return typesStore.byName[type]?.shape }
function isAutoPriced(row) {
  const t = typesStore.byName[row?.type]
  return !!(t && t.shape === 'security_auto' && row?.symbol)
}

function symbolPlaceholder(type) {
  const t = typesStore.byName[type]
  if (!t) return '可选'
  if (t.quote_source === 'stock') return '如 sh600519 / sz000001（或 6 位 A 股代码）'
  if (t.quote_source === 'fund') return '如 510300（6 位基金代码）'
  if (t.shape === 'security_manual') return '如 BTC / ETH（任意字符串）'
  return '可选'
}
function namePlaceholder(type) {
  return type ? `如：一笔${type}资产` : '请先选择类型'
}
function typeHint(type) {
  const t = typesStore.byName[type]
  if (!t) return '请选择一个类型；没有就去「⚙️ 类型管理」建一个'
  if (t.shape === 'security_auto') return `证券（自动行情·${t.quote_source}）：填代码+持仓+成本价，总成本和市值自动计算`
  if (t.shape === 'security_manual') return '证券（手填市值）：填代码+持仓+成本价，市值需手填'
  if (t.shape === 'cash') return '现金类：只需填余额，无成本和盈亏概念'
  return '一次性资产：直接填总成本和当前市值'
}
function valueLabel(type) {
  return shapeOf(type) === 'cash' ? '当前余额' : '当前市值'
}
function costLabel(_type) { return '总成本' }

const filterType = ref('')
const displayedAssets = computed(() => {
  if (!filterType.value) return props.assets
  return props.assets.filter(a => a.type === filterType.value)
})

const showDrawer = ref(false)
const drawerMode = ref('view')
const popoverRow = ref(null)
const editingRow = ref(null)
const refreshing = ref(false)

const editingSchema = computed(() => schemaOf(editingRow.value?.type))

const computedCostBasis = computed(() => {
  const r = editingRow.value
  if (!r) return 0
  const s = schemaOf(r.type)
  if (!s.showUnitCost) return Number(r.cost_basis) || 0
  const h = Number(r.holdings) || 0
  const cp = Number(r.cost_price) || 0
  return h * cp
})

const touchQuery = window.matchMedia('(hover: none) and (pointer: coarse)')
const isTouch = ref(touchQuery.matches)
function onTouchChange(e) { isTouch.value = e.matches }

// 移动端切换断点。桌面用 el-table，<= 768px 切换到卡片列表，
// 避免 8 列硬塞造成的横向溢出与文字挤压。
const mobileQuery = window.matchMedia('(max-width: 768px)')
const isMobile = ref(mobileQuery.matches)
function onMobileChange(e) { isMobile.value = e.matches }

onMounted(() => {
  touchQuery.addEventListener('change', onTouchChange)
  mobileQuery.addEventListener('change', onMobileChange)
})
onUnmounted(() => {
  touchQuery.removeEventListener('change', onTouchChange)
  mobileQuery.removeEventListener('change', onMobileChange)
})

// 移动端默认按现值降序，与桌面 el-table 默认排序一致
const sortedMobileAssets = computed(() => {
  return [...displayedAssets.value].sort(
    (a, b) => (b.current_value || 0) - (a.current_value || 0),
  )
})

watch(refreshCounter, () => {
  store.fetchAssets()
  store.fetchPortfolio()
})

// 初次挂载加载类型；类型被管理器增删后会触发 typesStore.refreshCounter，
// 投资模块无需重复订阅——AssetTable 同样依赖其下拉列表，所以这里直接看 types 数组即可
onMounted(() => typesStore.fetchTypes())

const showTypeManager = ref(false)

function handleRowClick(row, _col, event) {
  if (event?.target?.closest?.('.el-button, button, input, .el-select, .el-input, .el-date-editor')) return
  popoverRow.value = row
  drawerMode.value = 'view'
  showDrawer.value = true
  // 打开抽屉后异步加载市值历史；用户切换 days 也走同一入口
  if (canShowHistory(row)) loadHistory(row)
}

function onDrawerClose() {
  drawerMode.value = 'view'
  editingRow.value = null
  // 销毁 chart 实例避免泄漏
  if (historyChart) { historyChart.destroy(); historyChart = null }
  historyPoints.value = []
}

// ===== 市值历史折线 =====
const historyDays = ref(30)
const historyLoading = ref(false)
const historyPoints = ref([])
const historyChartRef = ref(null)
let historyChart = null

function canShowHistory(row) {
  if (!row) return false
  const s = schemaOf(row.type)
  // 现金类 / 一次性资产无价格波动概念
  return s.hasCost && (row.holdings || 0) > 0
}

async function loadHistory(row) {
  if (!row?.id) return
  historyLoading.value = true
  let points = []
  try {
    const res = await api.get(`/api/investment/assets/${row.id}/history`,
                              { params: { days: historyDays.value } })
    points = res.data?.points || []
  } catch {
    points = []
  }
  // 关键顺序：先把 loading 切 false 让 canvas 进入 DOM，再 nextTick + render
  // 否则 chart.js 会 attach 到一个 v-if 还没渲染出来的 canvas（ref=null），
  // 表现为"图表面积空白"。
  historyPoints.value = points
  historyLoading.value = false
  await nextTick()
  renderHistoryChart()
}

function renderHistoryChart() {
  if (!historyChartRef.value || !historyPoints.value.length) return
  if (historyChart) { historyChart.destroy(); historyChart = null }
  // 1 个点时画不出线段：复制一份让 chart 显示一条水平短线
  const src = historyPoints.value.length === 1
    ? [historyPoints.value[0], historyPoints.value[0]]
    : historyPoints.value
  const labels = src.map(p => (p.recorded_at || '').slice(5, 10) || '—')
  const data = src.map(p => p.value)
  historyChart = new Chart(historyChartRef.value.getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: '市值',
        data,
        borderColor: '#19c8b9',
        backgroundColor: 'rgba(25, 200, 185, 0.15)',
        tension: 0.35,
        fill: true,
        pointRadius: 4,
        pointBackgroundColor: '#11a89b',
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: (ctx) => `¥${Number(ctx.parsed.y).toFixed(2)}` },
        },
      },
      scales: {
        y: {
          ticks: { color: '#725d42', callback: (v) => '¥' + v },
          grid: { color: 'rgba(196, 184, 158, 0.25)' },
        },
        x: {
          ticks: { color: '#725d42', maxRotation: 0, autoSkipPadding: 12 },
          grid: { display: false },
        },
      },
    },
  })
}

function openCreate() {
  if (!assetTypes.value.length) {
    ElMessage.warning('还没有资产类型，请先点击「⚙️ 类型管理」创建')
    showTypeManager.value = true
    return
  }
  editingRow.value = {
    id: null, name: '', type: assetTypes.value[0].name, symbol: '',
    holdings: 0, cost_basis: 0, cost_price: 0, current_value: 0, notes: '',
  }
  popoverRow.value = null
  drawerMode.value = 'edit'
  showDrawer.value = true
}

function startDrawerEdit() {
  const r = popoverRow.value
  const s = schemaOf(r.type)
  const holdings = r.holdings || 0
  const costBasis = r.cost_basis || 0
  const costPrice = s.showUnitCost && holdings > 0
    ? Number((costBasis / holdings).toFixed(4))
    : 0
  editingRow.value = {
    id: r.id,
    name: r.name,
    type: r.type,
    symbol: r.symbol || '',
    holdings,
    cost_basis: costBasis,
    cost_price: costPrice,
    current_value: r.current_value || 0,
    notes: r.notes || '',
  }
  drawerMode.value = 'edit'
}

function cancelEdit() {
  if (popoverRow.value) {
    drawerMode.value = 'view'
    editingRow.value = null
  } else {
    showDrawer.value = false
  }
}

async function saveDrawerEdit() {
  const r = editingRow.value
  if (!r.name) { ElMessage.warning('请填写资产名称'); return }
  const s = schemaOf(r.type)

  if (s.autoQuote && r.holdings > 0 && !r.symbol) {
    ElMessage.warning(`「${r.type}」需填写代码，系统才能按行情源自动同步市值`)
    return
  }

  try {
    const payload = { ...r }

    // 按类型清洗字段
    if (s.showUnitCost) {
      payload.cost_basis = computedCostBasis.value
    }
    if (s.autoQuote) {
      delete payload.current_value  // 由后端按代码算
    }
    if (!s.hasCost) {
      // 现金：成本 = 余额，盈亏恒为 0
      payload.cost_basis = Number(r.current_value) || 0
    }
    if (!s.showSymbol) payload.symbol = ''
    if (!s.showHoldings) payload.holdings = 0
    delete payload.cost_price

    if (r.id) {
      await store.updateAsset(r.id, payload)
      ElMessage.success('已更新')
      const fresh = store.assets.find(a => a.id === r.id)
      if (fresh) popoverRow.value = fresh
      drawerMode.value = 'view'
    } else {
      await store.createAsset(payload)
      ElMessage.success('已添加')
      showDrawer.value = false
    }
    store.bumpRefresh()
  } catch (e) {
    const msg = e?.response?.data?.error || e?.response?.data?.message || '保存失败'
    ElMessage.error(msg)
  }
}

async function deleteFromDrawer() {
  try {
    await ElMessageBox.confirm(
      `确定删除「${popoverRow.value.name}」？相关交易流水也会一并删除。`,
      '确认删除', { type: 'warning' },
    )
    await store.deleteAsset(popoverRow.value.id)
    ElMessage.success('已删除')
    showDrawer.value = false
    store.bumpRefresh()
  } catch { /* 取消 */ }
}

// ===== 卖出 / 归档 =====

function canSell(row) {
  if (!row) return false
  const s = schemaOf(row.type)
  // 只对有"持仓 + 成本"概念的资产开放卖出（cash / lump 一次性资产走"归档"）
  return s.showHoldings && s.hasCost && (row.holdings || 0) > 0
}

const showSellDialog = ref(false)
const sellTarget = ref(null)
const selling = ref(false)
const sellForm = ref({ price: 0, quantity: 0, fee: 0, date: '', note: '' })

const sellUnitCost = computed(() => {
  const r = sellTarget.value
  if (!r) return 0
  const h = Number(r.holdings) || 0
  if (h <= 0) return 0
  return (Number(r.cost_basis) || 0) / h
})
const sellLatestPrice = computed(() => {
  const r = sellTarget.value
  if (!r) return 0
  const h = Number(r.holdings) || 0
  if (h <= 0) return 0
  return (Number(r.current_value) || 0) / h
})

const sellPreview = computed(() => {
  const r = sellTarget.value
  if (!r) return null
  const price = Number(sellForm.value.price) || 0
  const fee = Number(sellForm.value.fee) || 0
  const requested = Number(sellForm.value.quantity) || 0
  const qty = requested > 0 ? requested : (Number(r.holdings) || 0)
  if (qty <= 0 || price <= 0) return null
  const proceeds = price * qty - fee
  const cost = (Number(r.cost_basis) || 0) * qty / (Number(r.holdings) || 1)
  return { proceeds, cost, pnl: proceeds - cost }
})

function openSellDialog() {
  const r = popoverRow.value
  if (!canSell(r)) {
    ElMessage.warning('该资产类型不支持卖出，请使用「归档」')
    return
  }
  sellTarget.value = r
  // 默认价格用最新市价（若有），数量留空 = 全部
  sellForm.value = {
    price: sellLatestPrice.value || 0,
    quantity: 0,
    fee: 0,
    date: new Date().toISOString().slice(0, 10),
    note: '',
  }
  showSellDialog.value = true
}

async function confirmSell() {
  if (!sellTarget.value) return
  if (!(Number(sellForm.value.price) > 0)) {
    ElMessage.warning('请填写卖出价')
    return
  }
  selling.value = true
  try {
    const res = await store.sellAsset(sellTarget.value.id, {
      price: Number(sellForm.value.price),
      quantity: Number(sellForm.value.quantity) || 0,
      fee: Number(sellForm.value.fee) || 0,
      date: sellForm.value.date,
      note: sellForm.value.note,
    })
    showSellDialog.value = false
    showDrawer.value = false
    if (res.ledger === 'income') {
      ElMessage.success(`已卖出，盈利 +¥${res.pnl.toFixed(2)} 计入收入`)
    } else if (res.ledger === 'expense') {
      ElMessage.warning(`已卖出，亏损 ¥${Math.abs(res.pnl).toFixed(2)} 计入支出`)
    } else {
      ElMessage.success('已卖出，本次盈亏为 0')
    }
    store.bumpRefresh()
  } catch (e) {
    const msg = e?.response?.data?.error || e?.response?.data?.message || '卖出失败'
    ElMessage.error(msg)
  } finally {
    selling.value = false
  }
}

async function archiveFromDrawer() {
  const r = popoverRow.value
  if (!r) return
  try {
    await ElMessageBox.confirm(
      `按当前市值 ¥${(r.current_value || 0).toFixed(2)} 一次性结算「${r.name}」？资产将从列表移除，` +
      `盈亏会计入「投资盈利/亏损」分类。`,
      '确认归档', { type: 'info' },
    )
    const res = await store.archiveAsset(r.id, {})
    showDrawer.value = false
    if (res.ledger === 'income') {
      ElMessage.success(`已归档，盈利 +¥${res.pnl.toFixed(2)} 计入收入`)
    } else if (res.ledger === 'expense') {
      ElMessage.warning(`已归档，亏损 ¥${Math.abs(res.pnl).toFixed(2)} 计入支出`)
    } else {
      ElMessage.success('已归档，本次盈亏为 0')
    }
    store.bumpRefresh()
  } catch { /* 取消 */ }
}

async function refreshPrices() {
  refreshing.value = true
  try {
    const res = await store.refreshPrices()
    if (res?.updated > 0) {
      ElMessage.success(`已刷新 ${res.updated} 项行情`)
    } else {
      ElMessage.info('未更新任何资产（无股票/基金或缺代码/持仓）')
    }
    store.bumpRefresh()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || '行情刷新失败')
  } finally {
    refreshing.value = false
  }
}

function unitCostStr(row) {
  const s = schemaOf(row?.type)
  if (!s.showUnitCost) return '—'
  const h = Number(row?.holdings) || 0
  const cb = Number(row?.cost_basis) || 0
  if (h <= 0) return '—'
  return (cb / h).toFixed(4)
}
function unitCostNum(row) {
  const s = schemaOf(row?.type)
  const h = Number(row?.holdings) || 0
  const cb = Number(row?.cost_basis) || 0
  if (!s.showUnitCost || h <= 0) return 0
  return cb / h
}
function sortByUnitCost(a, b) { return unitCostNum(a) - unitCostNum(b) }

function pnl(row) {
  const s = schemaOf(row?.type)
  if (!s.hasCost) return null
  const cost = row?.cost_basis || 0
  const value = row?.current_value || 0
  if (!cost) return null
  const diff = value - cost
  const pct = diff / cost * 100
  return { diff, pct }
}
function pnlStr(row) {
  const p = pnl(row)
  if (!p) return '—'
  const sign = p.diff >= 0 ? '+' : ''
  return `${sign}${p.diff.toFixed(2)} (${sign}${p.pct.toFixed(1)}%)`
}
function pnlClass(row) {
  const p = pnl(row); if (!p) return ''
  return p.diff >= 0 ? 'up' : 'down'
}
function sortByPnl(a, b) {
  const pa = pnl(a); const pb = pnl(b)
  return (pa?.pct ?? -Infinity) - (pb?.pct ?? -Infinity)
}

function formatTime(iso) {
  if (!iso) return ''
  return String(iso).replace('T', ' ').slice(0, 16)
}
</script>

<style scoped>
.header-row {
  display: flex; justify-content: space-between; align-items: center; width: 100%;
  gap: 12px;
}
.header-title { font-weight: 600; flex-shrink: 0; }
.header-actions { display: flex; gap: 8px; align-items: center; min-width: 0; }
.header-buttons { display: flex; gap: 8px; align-items: center; }
.type-filter { width: 140px; }
.header-btn { white-space: nowrap; }
.btn-emoji { margin-right: 4px; }
/* 涨/盈用深红、跌/亏用深绿（A 股配色），对比度均 ≥ 4.5:1 满足 WCAG AA */
.up { color: #DC2626; font-weight: 600; }
.down { color: #15803D; font-weight: 600; }

.value-cell { display: inline-flex; gap: 4px; align-items: center; justify-content: flex-end; }
.auto-tag { font-size: 10px; height: 18px; line-height: 16px; padding: 0 4px; }

:deep(.asset-drawer) {
  border-radius: 16px 16px 0 0 !important;
  box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.12) !important;
}
:deep(.asset-drawer .el-drawer__body) {
  padding: 0;
  display: flex;
  flex-direction: column;
}

.drawer-handle-bar {
  width: 36px; height: 4px; background: #d1d5db;
  border-radius: 2px; margin: 10px auto 0; flex-shrink: 0;
}

.drawer-body {
  padding: 8px 24px 12px; display: flex; flex-direction: column; flex: 1;
  overflow-y: auto;
}
.drawer-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 13px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.drawer-row:last-child { border-bottom: none; }
.drawer-label { font-size: 13px; color: var(--color-text-muted); font-weight: 500; }
.drawer-value { font-size: 15px; font-weight: 600; max-width: 65%; text-align: right; word-break: break-all; }
.drawer-value.text-normal { font-weight: 400; color: var(--color-text); }
.drawer-value.text-muted  { font-weight: 400; color: var(--color-text-muted); }

.drawer-edit-title { font-size: 15px; font-weight: 600; padding: 14px 24px 6px; flex-shrink: 0; }
.drawer-edit-form {
  padding: 4px 24px 0; display: flex; flex-direction: column; gap: 14px;
  flex: 1; overflow-y: auto;
}
.drawer-edit-field { display: flex; flex-direction: column; gap: 5px; }
.drawer-edit-label { font-size: 12px; color: var(--color-text-muted); font-weight: 500; }
.required-hint { color: var(--color-primary); font-weight: 400; }
.type-hint {
  font-size: 11px; color: var(--color-text-muted); margin-top: 2px;
}
.auto-value-hint {
  font-size: 12px; color: var(--color-text-muted);
  padding: 8px 12px; background: var(--color-primary-light); border-radius: 6px;
}

/* 市值历史折线区域 */
.asset-history {
  padding: 12px 0 4px;
  border-top: 1px solid var(--color-border-light);
  margin-top: 6px;
}
.asset-history-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.asset-history-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text-strong);
}
.asset-history-chart {
  width: 100% !important;
  height: 160px !important;
}
.asset-history-empty, .asset-history-loading {
  font-size: 12px;
  color: var(--color-text-muted);
  text-align: center;
  padding: 22px 0;
}
.asset-history-note {
  font-size: 11px;
  color: var(--color-text-muted);
  text-align: center;
  margin-top: 4px;
  padding: 4px 8px;
  background: var(--color-surface-2);
  border-radius: 8px;
  display: inline-block;
}

.drawer-footer {
  display: flex; gap: 10px; padding: 14px 24px 28px;
  border-top: 1px solid var(--el-border-color-lighter); flex-shrink: 0;
}
.drawer-action-btn { flex: 1; }

/* 抽屉 footer 4 个动作按钮：PC 一行平分；窄屏 2×2 网格保证对齐
   不依赖 flex-wrap 防止 element-plus button 间不一致 margin 导致错位 */
.drawer-footer-actions {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}
.drawer-footer-actions .drawer-action-btn {
  width: 100%;
  margin: 0 !important;  /* 覆盖 element-plus 默认 button + button margin-left:12px */
  padding: 0 8px;
  min-width: 0;
}
@media (max-width: 540px) {
  .drawer-footer-actions {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* 卖出对话框 */
.sell-form { display: flex; flex-direction: column; gap: 8px; }
.sell-info {
  background: var(--color-bg);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
}
.sell-info-line { color: var(--color-text-muted); font-size: 12px; margin-top: 4px; }
.form-hint { font-size: 12px; color: var(--color-text-muted); margin-top: 2px; }
.sell-preview {
  background: var(--color-surface-2);
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.sell-preview-row { display: flex; justify-content: space-between; }
.sell-preview-row.pnl-up { color: #DC2626; font-weight: 600; }
.sell-preview-row.pnl-down { color: #15803D; font-weight: 600; }

/* 移动端卡片列表 */
.mobile-asset-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.mobile-asset-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.mobile-asset-card:active {
  background: var(--color-surface-2);
  border-color: var(--color-primary, var(--color-primary));
}

.mobile-card-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  gap: 8px;
}
.mobile-card-head {
  /* 第一行加大字号、靠上拉一点 */
  margin-bottom: 2px;
}
.mobile-card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
}
.mobile-asset-name {
  font-weight: 600;
  font-size: 15px;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mobile-type-tag {
  flex-shrink: 0;
  font-size: 11px !important;
  height: 20px !important;
  line-height: 18px !important;
  padding: 0 6px !important;
}

.mobile-card-pnl {
  font-weight: 600;
  font-size: 14px;
  white-space: nowrap;
  flex-shrink: 0;
}

.mobile-card-label { color: var(--color-text-muted); font-size: 12px; }
.mobile-card-value {
  font-weight: 600;
  font-size: 14px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.mobile-card-meta {
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-start;
}
.mobile-meta-pill {
  background: var(--color-bg, var(--color-bg));
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 2px 10px;
  font-size: 11px;
  color: var(--color-text-muted);
  white-space: nowrap;
}

.mobile-empty {
  text-align: center;
  color: var(--color-text-muted);
  padding: 32px 12px;
  font-size: 13px;
}

/* 移动端 header：标题独占一行；类型筛选独占一行；3 个动作按钮一行平分 */
@media (max-width: 768px) {
  .header-row {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }
  .header-title { font-size: 14px; }
  .header-actions {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
    width: 100%;
  }
  .type-filter { width: 100%; }
  .header-buttons {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 6px;
  }
  .header-btn {
    /* 让 3 个按钮等宽，emoji + 文字均居中显示 */
    width: 100%;
    padding: 0 4px;
    min-width: 0;
  }
  .btn-label {
    /* 极窄屏（< 360px）只剩 emoji 也能识别功能 */
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

/* 极窄机型再压一压字号 */
@media (max-width: 360px) {
  .header-btn .btn-label { font-size: 12px; }
}
</style>
