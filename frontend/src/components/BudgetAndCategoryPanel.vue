<template>
  <el-card>
    <template #header>
      <div class="bp-header">
        <span>预算 &amp; 分类管理</span>
        <el-button size="small" plain @click="openCalibrate">🤖 AI 校准建议</el-button>
      </div>
    </template>

    <!-- 周期 + 期间选择 -->
    <div class="section-label">预算周期</div>
    <div class="bp-period-bar">
      <el-radio-group v-model="cycle" size="small" @change="fetchBudgets">
        <el-radio-button label="monthly">月度</el-radio-button>
        <el-radio-button label="yearly">年度</el-radio-button>
      </el-radio-group>
      <el-date-picker
        v-if="cycle === 'monthly'"
        v-model="selectedMonth"
        type="month"
        value-format="YYYY-MM"
        placeholder="选择月份"
        @change="fetchBudgets"
        style="flex: 1; min-width: 130px;"
      />
      <el-date-picker
        v-else
        v-model="selectedYear"
        type="year"
        value-format="YYYY"
        placeholder="选择年份"
        @change="fetchBudgets"
        style="flex: 1; min-width: 130px;"
      />
    </div>

    <!-- 预算表 -->
    <el-table :data="budgets" size="small" class="budget-table" style="width: 100%"
      @selection-change="selectedBudgets = $event">
      <el-table-column type="selection" width="36" />
      <el-table-column prop="category" label="分类" />
      <el-table-column prop="amount" label="预算额">
        <template #default="scope">
          <span class="amount-text">¥{{ scope.row.amount }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remaining" label="剩余预算">
        <template #default="scope">
          <span :class="scope.row.remaining < 0 ? 'amount-expense' : 'amount-income'">
            {{ scope.row.remaining < 0 ? `-¥${Math.abs(scope.row.remaining)}` : `¥${scope.row.remaining}` }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="" width="48" align="center">
        <template #default="scope">
          <el-button
            type="danger" size="small" :icon="Delete" circle
            @click="deleteBudget(scope.row.category)"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- 批量操作栏 -->
    <div v-if="selectedBudgets.length" class="bulk-action-bar">
      <span class="selected-hint">已选 {{ selectedBudgets.length }} 项</span>
      <el-button type="danger" size="small" @click="deleteBulk">批量删除</el-button>
    </div>

    <!-- 添加/更新预算 -->
    <div class="budget-form">
      <div class="section-label" style="margin-top: 14px;">设置预算</div>
      <div class="budget-inputs">
        <el-select v-model="budgetForm.category" placeholder="选择分类" style="flex: 1">
          <el-option v-for="cat in expenseCategories" :key="cat" :label="cat" :value="cat" />
        </el-select>
        <el-input-number v-model="budgetForm.amount" :min="0" style="flex: 1; min-width: 100px;" />
        <el-button type="primary" size="small" @click="submitBudget">确定</el-button>
      </div>
    </div>

    <el-divider style="margin: 16px 0;" />

    <!-- 分类管理 -->
    <el-tabs v-model="activeTab">
      <el-tab-pane label="支出分类" name="支出">
        <CategoryManager type="expense" />
      </el-tab-pane>
      <el-tab-pane label="收入分类" name="收入">
        <CategoryManager type="income" />
      </el-tab-pane>
    </el-tabs>
  </el-card>

  <!-- AI 预算校准对话框 -->
  <el-dialog
    v-model="calibrate.visible"
    title="🤖 AI 预算校准"
    :width="dialogWidth"
    append-to-body
  >
    <div class="cal-form">
      <div class="cal-form-row">
        <label>目标月份：</label>
        <el-date-picker
          v-model="calibrate.month"
          type="month" value-format="YYYY-MM"
          size="small" style="width: 140px"
          @change="loadCalibration"
        />
        <label style="margin-left: 12px">缓冲系数：</label>
        <el-input-number
          v-model="calibrate.inflation"
          :min="1.0" :max="2.0" :step="0.05" :precision="2"
          size="small" controls-position="right"
          style="width: 110px"
          @change="loadCalibration"
        />
      </div>
      <div class="cal-hint">
        基于过去 3 个月该分类的实际平均支出 × 缓冲系数。系数 1.05 表示在均值上留 5% 余量。
      </div>
    </div>

    <div v-if="calibrate.loading" class="cal-loading">分析中…</div>
    <div v-else-if="!calibrate.items.length" class="cal-empty">
      过去 3 个月没有足够的支出数据用来给出建议。再多记几笔吧～
    </div>
    <el-table v-else :data="calibrate.items" size="small" max-height="320" @selection-change="onCalSelChange">
      <el-table-column type="selection" width="40" />
      <el-table-column prop="category" label="分类" min-width="100" />
      <el-table-column label="3 月均值" align="right" width="100">
        <template #default="{ row }">¥{{ row.avg_spend_3m.toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="当前预算" align="right" width="100">
        <template #default="{ row }">
          <span v-if="row.current_budget">¥{{ row.current_budget.toFixed(2) }}</span>
          <span v-else class="cal-muted">未设</span>
        </template>
      </el-table-column>
      <el-table-column label="建议" align="right" width="100">
        <template #default="{ row }">
          <span class="cal-sugg">¥{{ row.suggested_budget.toFixed(2) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变化" align="right" width="80">
        <template #default="{ row }">
          <span v-if="row.delta_pct !== null"
                :class="row.delta_pct > 0 ? 'cal-up' : row.delta_pct < 0 ? 'cal-down' : ''">
            {{ row.delta_pct > 0 ? '+' : '' }}{{ row.delta_pct }}%
          </span>
          <span v-else class="cal-muted">—</span>
        </template>
      </el-table-column>
    </el-table>

    <div class="cal-total">
      <span class="cal-muted">合计建议预算</span>
      <strong>¥{{ calibrate.total.toFixed(2) }}</strong>
    </div>

    <template #footer>
      <el-button @click="calibrate.visible = false">取消</el-button>
      <el-button type="primary"
                 :disabled="!calibrate.selected.length"
                 :loading="calibrate.applying"
                 @click="applyCalibration">
        采纳 {{ calibrate.selected.length }} 条
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { storeToRefs } from 'pinia'
import api from '@/api'
import CategoryManager from './CategoryManager.vue'
import { useCategoryStore } from '@/stores/categories'

const categoryStore = useCategoryStore()
const { refreshCounter } = storeToRefs(categoryStore)

// ===== AI 预算校准 =====
const _mq = window.matchMedia('(max-width: 768px)')
const _isMobile = ref(_mq.matches)
function _onMq(e) { _isMobile.value = e.matches }
onMounted(() => _mq.addEventListener('change', _onMq))
onBeforeUnmount(() => _mq.removeEventListener('change', _onMq))
const dialogWidth = computed(() => _isMobile.value ? 'calc(100vw - 24px)' : '640px')

function _nextMonth(yyyymm) {
  const [y, m] = yyyymm.split('-').map(Number)
  return m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, '0')}`
}

const calibrate = reactive({
  visible: false,
  loading: false,
  applying: false,
  month: '',
  inflation: 1.05,
  items: [],
  total: 0,
  selected: [],
})

function openCalibrate() {
  // 默认建议"当前选中月份的下个月"——通常用户在月底设下月预算
  const base = (typeof selectedMonth !== 'undefined' && selectedMonth.value)
               || new Date().toISOString().slice(0, 7)
  calibrate.month = _nextMonth(base)
  calibrate.visible = true
  loadCalibration()
}

async function loadCalibration() {
  if (!calibrate.month) return
  calibrate.loading = true
  try {
    const res = await api.get('/api/budgets/calibrate', {
      params: { month: calibrate.month, inflation: calibrate.inflation },
      silent: true,
    })
    calibrate.items = res.data?.items || []
    calibrate.total = res.data?.total_suggested || 0
  } catch {
    calibrate.items = []
    calibrate.total = 0
  } finally {
    calibrate.loading = false
  }
}

function onCalSelChange(rows) {
  calibrate.selected = rows
}

async function applyCalibration() {
  if (!calibrate.selected.length) return
  calibrate.applying = true
  try {
    const res = await api.post('/api/budgets/calibrate/apply', {
      month: calibrate.month,
      items: calibrate.selected.map(r => ({
        category: r.category,
        suggested_budget: r.suggested_budget,
      })),
    })
    ElMessage.success(`已采纳 ${res.data?.applied || 0} 条建议预算到 ${calibrate.month}`)
    calibrate.visible = false
    // 如果用户选中月份正是 target，则刷新预算列表
    if (selectedMonth.value === calibrate.month) {
      await fetchBudgets()
    }
    categoryStore.bumpRefresh()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || '应用失败')
  } finally {
    calibrate.applying = false
  }
}
// 支出分类从 store 派生，CategoryManager 更新后自动响应
const expenseCategories = computed(() => categoryStore.expenseNames)

const selectedMonth = ref(new Date().toISOString().slice(0, 7))
const selectedYear = ref(String(new Date().getFullYear()))
const cycle = ref('monthly')
const budgets = ref([])
const activeTab = ref('支出')
const budgetForm = ref({ category: '', amount: 0 })
const selectedBudgets = ref([])

// 当前周期的期间键:月度 YYYY-MM / 年度 YYYY
function activePeriod() {
  return cycle.value === 'yearly' ? selectedYear.value : selectedMonth.value
}

async function fetchBudgets() {
  budgets.value = []
  // 分类列表从 store 取（缓存），预算仍需独立请求
  const [bRes] = await Promise.all([
    api.get('/api/budgets', { params: { period: activePeriod() } }),
    categoryStore.fetchCategories('expense'),
  ])
  budgets.value = bRes.data
}

async function submitBudget() {
  await api.post('/api/budgets', {
    category: budgetForm.value.category,
    amount: budgetForm.value.amount,
    period: activePeriod(),
  })
  await fetchBudgets()
  categoryStore.bumpRefresh()
}

async function deleteBulk() {
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${selectedBudgets.value.length} 条预算吗？`,
      '批量删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  const period = activePeriod()
  await Promise.all(
    selectedBudgets.value.map(row =>
      api.delete('/api/budgets', { data: { category: row.category, period } })
    )
  )
  selectedBudgets.value = []
  await fetchBudgets()
  categoryStore.bumpRefresh()
}

async function deleteBudget(category) {
  try {
    await ElMessageBox.confirm(`确定删除「${category}」的预算吗？`, '删除确认', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning'
    })
  } catch {
    return
  }
  await api.delete('/api/budgets', { data: { category, period: activePeriod() } })
  await fetchBudgets()
  categoryStore.bumpRefresh()
}

onMounted(fetchBudgets)
watch(refreshCounter, fetchBudgets)
</script>

<style scoped>
/* AI 预算校准 */
.bp-period-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.bp-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.cal-form {
  background: var(--color-surface-2);
  padding: 12px 14px;
  border-radius: 12px;
  margin-bottom: 14px;
  font-size: 13px;
}
.cal-form-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.cal-hint {
  margin-top: 8px;
  font-size: 11px;
  color: var(--color-text-muted);
  line-height: 1.6;
}
.cal-loading, .cal-empty {
  text-align: center;
  padding: 32px 0;
  color: var(--color-text-muted);
  font-size: 13px;
}
.cal-sugg { color: var(--color-primary-dark); font-weight: 700; }
.cal-muted { color: var(--color-text-muted); }
.cal-up { color: var(--color-up); font-weight: 600; }
.cal-down { color: var(--color-down); font-weight: 600; }
.cal-total {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 10px;
  padding: 10px 14px;
  background: var(--color-primary-light);
  border-radius: 10px;
  font-size: 13px;
}
.cal-total strong {
  font-size: 16px;
  font-weight: 800;
  color: var(--color-primary-dark);
  font-variant-numeric: tabular-nums;
}

.section-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}

.budget-table :deep(th.el-table__cell) {
  background: var(--color-surface-2) !important;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 600;
}

.amount-text { font-weight: 500; color: var(--color-text); }
.amount-expense { color: #ef4444; font-weight: 600; }
.amount-income  { color: #22c55e; font-weight: 600; }

.bulk-action-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0 4px;
}
.selected-hint {
  font-size: 13px;
  color: var(--color-text-muted);
}

.budget-inputs {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .budget-inputs {
    flex-direction: column;
    align-items: stretch;
  }
  .budget-inputs .el-button {
    width: 100%;
  }
  .budget-inputs :deep(.el-input-number) {
    width: 100% !important;
  }
}
</style>
