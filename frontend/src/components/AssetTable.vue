<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <span>📁 我的资产</span>
        <div class="header-actions">
          <el-button size="small" :loading="refreshing" @click="refreshPrices">
            🔄 刷新行情
          </el-button>
          <el-button size="small" type="primary" @click="openCreate">新增资产</el-button>
        </div>
      </div>
    </template>

    <el-table
      :data="assets"
      size="small"
      empty-text="还没有录入资产"
      style="width: 100%"
      @row-click="handleRowClick"
      :row-class-name="isTouch ? 'touch-tappable-row' : ''"
    >
      <el-table-column prop="name" label="名称" min-width="120" />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">{{ TYPE_LABEL[row.type] || row.type }}</template>
      </el-table-column>
      <el-table-column prop="symbol" label="代码" width="110">
        <template #default="{ row }">{{ row.symbol || '—' }}</template>
      </el-table-column>
      <el-table-column prop="holdings" label="数量" width="100" align="right">
        <template #default="{ row }">{{ row.holdings || '—' }}</template>
      </el-table-column>
      <el-table-column prop="cost_basis" label="成本" width="110" align="right">
        <template #default="{ row }">¥{{ (row.cost_basis || 0).toFixed(2) }}</template>
      </el-table-column>
      <el-table-column prop="current_value" label="现值" width="130" align="right">
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
      <el-table-column label="盈亏" width="120" align="right">
        <template #default="{ row }">
          <span :class="pnlClass(row)">{{ pnlStr(row) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 行详情 / 编辑抽屉，和账本记录一致的 view + edit 双模式 -->
    <el-drawer
      v-model="showDrawer"
      direction="btt"
      :with-header="false"
      :size="drawerMode === 'edit' ? '540px' : '400px'"
      class="asset-drawer"
      @close="onDrawerClose"
    >
      <div class="drawer-handle-bar"></div>

      <!-- VIEW 模式 -->
      <template v-if="drawerMode === 'view' && popoverRow">
        <div class="drawer-body">
          <div class="drawer-row">
            <span class="drawer-label">名称</span>
            <span class="drawer-value">{{ popoverRow.name }}</span>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">类型</span>
            <span class="drawer-value">{{ TYPE_LABEL[popoverRow.type] || popoverRow.type }}</span>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">代码</span>
            <span class="drawer-value text-normal">{{ popoverRow.symbol || '—' }}</span>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">持仓</span>
            <span class="drawer-value text-normal">{{ popoverRow.holdings || '—' }}</span>
          </div>
          <div v-if="isAutoType(popoverRow.type) && popoverRow.holdings > 0" class="drawer-row">
            <span class="drawer-label">成本价</span>
            <span class="drawer-value">¥{{ unitCostStr(popoverRow) }}</span>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">总成本</span>
            <span class="drawer-value">¥{{ (popoverRow.cost_basis || 0).toFixed(2) }}</span>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">当前市值</span>
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
          <div class="drawer-row">
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
        </div>
        <div class="drawer-footer">
          <el-button class="drawer-action-btn" plain type="danger" @click="deleteFromDrawer">
            🗑️ 删除
          </el-button>
          <el-button class="drawer-action-btn" type="primary" @click="startDrawerEdit">
            ✏️ 编辑
          </el-button>
        </div>
      </template>

      <!-- EDIT 模式 -->
      <template v-if="drawerMode === 'edit' && editingRow">
        <div class="drawer-edit-title">{{ editingRow.id ? '编辑资产' : '新增资产' }}</div>
        <div class="drawer-edit-form">
          <div class="drawer-edit-field">
            <label class="drawer-edit-label">名称</label>
            <el-input v-model="editingRow.name" placeholder="如：沪深300指数基金" />
          </div>
          <div class="drawer-edit-field">
            <label class="drawer-edit-label">类型</label>
            <el-select v-model="editingRow.type" style="width:100%">
              <el-option v-for="(label, key) in TYPE_LABEL" :key="key" :value="key" :label="label" />
            </el-select>
          </div>
          <div class="drawer-edit-field">
            <label class="drawer-edit-label">
              代码
              <span v-if="needsSymbol(editingRow.type)" class="required-hint">（建议填写，用于自动同步市值）</span>
            </label>
            <el-input
              v-model="editingRow.symbol"
              :placeholder="symbolPlaceholder(editingRow.type)"
            />
          </div>
          <div class="drawer-edit-field">
            <label class="drawer-edit-label">持仓数量</label>
            <el-input-number
              v-model="editingRow.holdings"
              :min="0"
              :step="1"
              controls-position="right"
              style="width:100%"
            />
          </div>
          <div v-if="isAutoType(editingRow.type)" class="drawer-edit-field">
            <label class="drawer-edit-label">
              成本价（每股/每份）
            </label>
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
          <div v-else class="drawer-edit-field">
            <label class="drawer-edit-label">总成本</label>
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
              当前市值
              <span v-if="isAutoType(editingRow.type)" class="required-hint">
                （股票/基金自动同步，无需填写）
              </span>
            </label>
            <el-input-number
              v-if="!isAutoType(editingRow.type)"
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
  </el-card>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { storeToRefs } from 'pinia'
import { useInvestmentStore } from '@/stores/investment'

const props = defineProps({ assets: { type: Array, default: () => [] } })
const store = useInvestmentStore()
const { refreshCounter } = storeToRefs(store)

const TYPE_LABEL = {
  stock: '股票', fund: '基金', bond: '债券', cash: '现金',
  crypto: '加密货币', realestate: '房地产', other: '其他',
}

const AUTO_TYPES = new Set(['stock', 'fund'])
const isAutoType = (t) => AUTO_TYPES.has(t)
const needsSymbol = (t) => AUTO_TYPES.has(t)
const isAutoPriced = (row) => AUTO_TYPES.has(row?.type) && !!row?.symbol

function symbolPlaceholder(type) {
  if (type === 'stock') return '如 sh600519 / sz000001（或 6 位 A 股代码）'
  if (type === 'fund') return '如 510300（6 位基金代码）'
  return '可选'
}

const showDrawer = ref(false)
const drawerMode = ref('view')
const popoverRow = ref(null)
const editingRow = ref(null)
const refreshing = ref(false)

const computedCostBasis = computed(() => {
  const r = editingRow.value
  if (!r || !isAutoType(r.type)) return r?.cost_basis || 0
  const h = Number(r.holdings) || 0
  const cp = Number(r.cost_price) || 0
  return h * cp
})

const touchQuery = window.matchMedia('(hover: none) and (pointer: coarse)')
const isTouch = ref(touchQuery.matches)
function onTouchChange(e) { isTouch.value = e.matches }

onMounted(() => touchQuery.addEventListener('change', onTouchChange))
onUnmounted(() => touchQuery.removeEventListener('change', onTouchChange))

watch(refreshCounter, () => {
  store.fetchAssets()
  store.fetchPortfolio()
})

function handleRowClick(row, _col, event) {
  if (event?.target?.closest?.('.el-button, button, input, .el-select, .el-input, .el-date-editor')) return
  popoverRow.value = row
  drawerMode.value = 'view'
  showDrawer.value = true
}

function onDrawerClose() {
  drawerMode.value = 'view'
  editingRow.value = null
}

function openCreate() {
  editingRow.value = {
    id: null, name: '', type: 'fund', symbol: '',
    holdings: 0, cost_basis: 0, cost_price: 0, current_value: 0, notes: '',
  }
  popoverRow.value = null
  drawerMode.value = 'edit'
  showDrawer.value = true
}

function startDrawerEdit() {
  const r = popoverRow.value
  const holdings = r.holdings || 0
  const costBasis = r.cost_basis || 0
  const costPrice = isAutoType(r.type) && holdings > 0
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
  if (isAutoType(r.type) && r.holdings > 0 && !r.symbol) {
    ElMessage.warning('股票/基金需填写代码，系统才能自动同步市值')
    return
  }
  try {
    const payload = { ...r }
    // 股票/基金：总成本由 持仓 × 成本价 算出；current_value 由后端算
    if (isAutoType(r.type)) {
      payload.cost_basis = computedCostBasis.value
      delete payload.current_value
    }
    delete payload.cost_price

    if (r.id) {
      await store.updateAsset(r.id, payload)
      ElMessage.success('已更新')
      // 重新抓当前行
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
  const h = Number(row?.holdings) || 0
  const cb = Number(row?.cost_basis) || 0
  if (h <= 0) return '—'
  return (cb / h).toFixed(4)
}

function pnl(row) {
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

function formatTime(iso) {
  if (!iso) return ''
  return String(iso).replace('T', ' ').slice(0, 16)
}
</script>

<style scoped>
.header-row {
  display: flex; justify-content: space-between; align-items: center; width: 100%;
}
.header-actions { display: flex; gap: 8px; }
.up { color: #EF4444; font-weight: 600; }
.down { color: #22C55E; font-weight: 600; }

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
.auto-value-hint {
  font-size: 12px; color: var(--color-text-muted);
  padding: 8px 12px; background: #F0F7FF; border-radius: 6px;
}

.drawer-footer {
  display: flex; gap: 10px; padding: 14px 24px 28px;
  border-top: 1px solid var(--el-border-color-lighter); flex-shrink: 0;
}
.drawer-action-btn { flex: 1; }
</style>
