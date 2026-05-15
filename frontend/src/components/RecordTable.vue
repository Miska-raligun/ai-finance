<!-- components/RecordTable.vue -->
<template>
  <div class="record-table-wrap">
    <div class="table-toolbar">
      <el-form :inline="true" size="small" class="filter-form">
        <el-form-item label="类型">
          <el-select v-model="filterCategory" placeholder="全部" clearable style="width: 120px">
            <el-option
              v-for="cat in categories"
              :key="cat"
              :label="cat"
              :value="cat"
            />
          </el-select>
        </el-form-item>

        <!-- 日期筛选：桌面端用 daterange，移动端用两个独立 date picker -->
        <template v-if="!isNarrow">
          <el-form-item label="时间范围">
            <el-date-picker
              v-model="dateRange"
              type="daterange"
              start-placeholder="开始"
              end-placeholder="结束"
              value-format="YYYY-MM-DD"
              style="width: 240px"
            />
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item label="开始日期">
            <el-date-picker
              v-model="startDate"
              type="date"
              placeholder="开始日期"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="结束日期">
            <el-date-picker
              v-model="endDate"
              type="date"
              placeholder="结束日期"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </el-form-item>
        </template>
      </el-form>

      <div class="filter-actions">
        <el-button type="primary" size="small" @click="applyFilter">筛选</el-button>
        <el-button plain size="small" @click="resetFilters">全部</el-button>
        <el-button type="danger" size="small" @click="deleteSelected" :disabled="!selectedRows.length">
          删除所选{{ selectedRows.length ? `(${selectedRows.length})` : '' }}
        </el-button>
      </div>
    </div>

    <el-table
      :data="records"
      stripe
      style="width: 100%"
      @selection-change="handleSelectionChange"
      @row-click="handleRowClick"
      @sort-change="handleSortChange"
      :row-class-name="isTouch ? 'touch-tappable-row' : ''"
      class="record-table"
    >
      <el-table-column type="selection" width="46" />
      <el-table-column prop="category" label="类型" min-width="80">
        <template #default="scope">
          <template v-if="editingId === scope.row.id">
            <el-select v-model="scope.row.category" style="width: 100px">
              <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
            </el-select>
          </template>
          <template v-else>
            <el-tag size="small" type="info" class="cat-tag">{{ scope.row.category }}</el-tag>
          </template>
        </template>
      </el-table-column>
      <el-table-column v-if="!isNarrow" prop="note" label="备注" min-width="90">
        <template #default="scope">
          <template v-if="editingId === scope.row.id">
            <el-input v-model="scope.row.note" size="small" />
          </template>
          <template v-else>{{ scope.row.note }}</template>
        </template>
      </el-table-column>
      <el-table-column v-if="showDateColumn" prop="date" label="日期" sortable="custom" min-width="100">
        <template #default="scope">
          <template v-if="editingId === scope.row.id">
            <el-date-picker v-model="scope.row.date" type="date" value-format="YYYY-MM-DD" style="width:130px" />
          </template>
          <template v-else>{{ scope.row.date }}</template>
        </template>
      </el-table-column>
      <el-table-column prop="amount" :label="showBudget ? '支出金额' : '收入金额'" sortable="custom" min-width="90">
        <template #default="scope">
          <template v-if="editingId === scope.row.id">
            <el-input-number v-model="scope.row.amount" :min="0" style="width:120px" />
          </template>
          <template v-else>
            <span :class="showBudget ? 'amount-expense' : 'amount-income'">
              ¥{{ scope.row.amount }}
            </span>
            <el-tooltip
              v-if="showBudget && scope.row.anomaly_flag"
              :content="`异常分值 ${Number(scope.row.anomaly_score || 0).toFixed(1)}：金额显著偏离同分类历史均值`"
              placement="top"
            >
              <el-tag size="small" type="danger" effect="plain" class="anomaly-tag">🚨 异常</el-tag>
            </el-tooltip>
          </template>
        </template>
      </el-table-column>
      <el-table-column v-if="showBudget && !isNarrow" prop="left_budget" label="剩余预算" sortable="custom" min-width="90">
        <template #default="scope">
          <span v-if="scope.row.left_budget === '—'" style="color: var(--color-text-muted)">—</span>
          <span v-else :class="scope.row.left_budget < 0 ? 'amount-expense' : 'amount-income'">
            {{ scope.row.left_budget < 0 ? `-¥${Math.abs(scope.row.left_budget)}` : `¥${scope.row.left_budget}` }}
          </span>
        </template>
      </el-table-column>
      <!-- 操作列：仅桌面端显示（移动端通过抽屉编辑） -->
      <el-table-column v-if="!isNarrow" label="操作" width="130" fixed="right">
        <template #default="scope">
          <template v-if="editingId === scope.row.id">
            <el-button size="small" type="primary" @click="saveEdit(scope.row)">保存</el-button>
            <el-button size="small" @click="cancelEdit">取消</el-button>
          </template>
          <template v-else>
            <el-button size="small" @click="startEdit(scope.row)">编辑</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <!-- 桌面端：完整分页 -->
    <el-pagination
      v-if="!isNarrow"
      background
      layout="prev, pager, next, total"
      :total="totalRecords"
      :page-size="pageSize"
      :current-page="currentPage"
      @current-change="handlePageChange"
      class="table-pagination"
    />

    <!-- 移动端：紧凑分页，支持下拉选页 -->
    <div v-else class="mobile-pagination">
      <el-button
        size="small"
        :disabled="currentPage <= 1"
        @click="handlePageChange(currentPage - 1)"
      >‹ 上一页</el-button>

      <el-select
        v-model="currentPage"
        size="small"
        style="width: 110px"
        @change="handlePageChange(currentPage)"
      >
        <el-option
          v-for="p in totalPages"
          :key="p"
          :label="`第 ${p} 页`"
          :value="p"
        />
      </el-select>

      <span class="page-total-hint">共 {{ totalPages }} 页</span>

      <el-button
        size="small"
        :disabled="currentPage >= totalPages"
        @click="handlePageChange(currentPage + 1)"
      >下一页 ›</el-button>
    </div>

    <!-- 行详情抽屉（支持查看 / 编辑两种模式） -->
    <el-drawer
      v-model="showPopover"
      direction="btt"
      :with-header="false"
      :size="drawerMode === 'edit' ? '420px' : (showBudget ? '360px' : '320px')"
      class="row-detail-drawer"
      @close="onDrawerClose"
    >
      <div class="drawer-handle-bar"></div>

      <!-- VIEW 模式：只读展示 + 操作按钮 -->
      <template v-if="drawerMode === 'view' && popoverRow">
        <div class="drawer-detail-body">
          <div class="drawer-detail-row">
            <span class="drawer-detail-label">分类</span>
            <el-tag size="small" type="info" class="cat-tag">{{ popoverRow.category }}</el-tag>
          </div>
          <div class="drawer-detail-row">
            <span class="drawer-detail-label">金额</span>
            <span :class="showBudget ? 'drawer-detail-value amount-expense' : 'drawer-detail-value amount-income'">
              ¥{{ popoverRow.amount }}
              <el-tag
                v-if="showBudget && popoverRow.anomaly_flag"
                size="small"
                type="danger"
                effect="plain"
                class="anomaly-tag"
              >🚨 异常</el-tag>
            </span>
          </div>
          <div class="drawer-detail-row">
            <span class="drawer-detail-label">日期</span>
            <span class="drawer-detail-value text-normal">{{ popoverRow.date }}</span>
          </div>
          <div class="drawer-detail-row">
            <span class="drawer-detail-label">备注</span>
            <span class="drawer-detail-value text-normal">{{ popoverRow.note || '—' }}</span>
          </div>
          <div v-if="showBudget" class="drawer-detail-row">
            <span class="drawer-detail-label">剩余预算</span>
            <span
              class="drawer-detail-value"
              :class="
                popoverRow.left_budget === '—' ? 'text-muted'
                : popoverRow.left_budget < 0   ? 'amount-expense'
                : 'amount-income'
              "
            >
              {{
                popoverRow.left_budget === '—'
                  ? '—'
                  : popoverRow.left_budget < 0
                    ? `-¥${Math.abs(popoverRow.left_budget)}`
                    : `¥${popoverRow.left_budget}`
              }}
            </span>
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

      <!-- EDIT 模式：全字段表单 -->
      <template v-if="drawerMode === 'edit' && editingRow">
        <div class="drawer-edit-title">编辑记录</div>
        <div class="drawer-edit-form">
          <div class="drawer-edit-field">
            <label class="drawer-edit-label">分类</label>
            <el-select v-model="editingRow.category" style="width: 100%">
              <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
            </el-select>
          </div>
          <div class="drawer-edit-field">
            <label class="drawer-edit-label">金额</label>
            <el-input-number
              v-model="editingRow.amount"
              :min="0"
              controls-position="right"
              style="width: 100%"
            />
          </div>
          <div class="drawer-edit-field">
            <label class="drawer-edit-label">日期</label>
            <el-date-picker
              v-model="editingRow.date"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </div>
          <div class="drawer-edit-field">
            <label class="drawer-edit-label">备注</label>
            <el-input v-model="editingRow.note" placeholder="可选" />
          </div>
        </div>
        <div class="drawer-footer">
          <el-button class="drawer-action-btn" plain @click="drawerMode = 'view'">取消</el-button>
          <el-button class="drawer-action-btn" type="primary" @click="saveDrawerEdit">保存</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { storeToRefs } from 'pinia'
import api from '@/api'
import { useCategoryStore } from '@/stores/categories'

const props = defineProps({
  type: { type: String, default: 'expense' },
  title: { type: String, default: '记录表格' },
  showBudget: { type: Boolean, default: true }
})

const categoryStore = useCategoryStore()
const { refreshCounter } = storeToRefs(categoryStore)

const records = ref([])
const totalRecords = ref(0)
// 分类列表：从 store 派生，按当前 type 挑选对应数组
const categories = computed(() =>
  props.type === 'expense' ? categoryStore.expenseNames : categoryStore.incomeNames
)
const filterCategory = ref('')
const today = new Date().toISOString().slice(0, 10)

// 桌面端 daterange
const dateRange = ref([today, today])
// 移动端独立 date
const startDate = ref(today)
const endDate = ref(today)

const selectedRows = ref([])
const editingId = ref(null)
const pageSize = 10
const currentPage = ref(1)
const sortBy = ref('')
const sortOrder = ref('')

// 触控能力检测（手机 + 平板）：决定是否支持触摸行弹出详情
const touchQuery = window.matchMedia('(hover: none) and (pointer: coarse)')
const isTouch = ref(touchQuery.matches)
function onTouchChange(e) { isTouch.value = e.matches }

// 窄屏检测（仅手机）：决定是否隐藏列、紧凑分页、独立日期选择器
const isNarrow = ref(window.innerWidth < 768)
function onResize() { isNarrow.value = window.innerWidth < 768 }

onMounted(() => {
  touchQuery.addEventListener('change', onTouchChange)
  window.addEventListener('resize', onResize)
})
onUnmounted(() => {
  touchQuery.removeEventListener('change', onTouchChange)
  window.removeEventListener('resize', onResize)
})

// 日期列：桌面始终显示；手机在无筛选（全部）或多天范围时显示
const showDateColumn = computed(() => {
  if (!isNarrow.value) return true
  const sd = startDate.value
  const ed = endDate.value
  if (!sd && !ed) return true  // 全部（无日期筛选）
  return !!(sd && ed && sd !== ed)  // 跨多天范围
})

// 行详情抽屉状态
const popoverRow = ref(null)
const showPopover = ref(false)
const drawerMode = ref('view')   // 'view' | 'edit'
const editingRow = ref(null)     // 抽屉编辑副本

function handleRowClick(row, column, event) {
  if (editingId.value !== null) return
  if (event.target.closest('.el-button, button, input, .el-select, .el-input, .el-date-editor')) return
  popoverRow.value = row
  showPopover.value = true
}

function onDrawerClose() {
  drawerMode.value = 'view'
  editingRow.value = null
}

function startDrawerEdit() {
  editingRow.value = { ...popoverRow.value }
  drawerMode.value = 'edit'
}

async function saveDrawerEdit() {
  const url = props.type === 'expense'
    ? `/api/records/${editingRow.value.id}`
    : `/api/income/${editingRow.value.id}`
  try {
    await api.put(url, editingRow.value)
    const idx = records.value.findIndex(r => r.id === editingRow.value.id)
    if (idx !== -1) records.value[idx] = { ...editingRow.value }
    popoverRow.value = { ...editingRow.value }
    drawerMode.value = 'view'
    categoryStore.bumpRefresh()
  } catch {
    ElMessage.error('保存失败，请重试')
  }
}

async function deleteFromDrawer() {
  try {
    await ElMessageBox.confirm('确定删除这条记录吗？', '删除确认', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning'
    })
  } catch { return }
  const url = props.type === 'expense'
    ? `/api/records/${popoverRow.value.id}`
    : `/api/income/${popoverRow.value.id}`
  await api.delete(url)
  records.value = records.value.filter(r => r.id !== popoverRow.value.id)
  totalRecords.value = Math.max(0, totalRecords.value - 1)
  showPopover.value = false
  categoryStore.bumpRefresh()
}

const totalPages = computed(() => Math.max(1, Math.ceil(totalRecords.value / pageSize)))

function handlePageChange(val) {
  currentPage.value = val
  fetchData()
}

function resetFilters() {
  filterCategory.value = ''
  dateRange.value = []
  startDate.value = ''
  endDate.value = ''
  currentPage.value = 1
  fetchData()
}

function handleSortChange({ prop, order }) {
  sortBy.value = order ? prop : ''
  sortOrder.value = order === 'ascending' ? 'ASC' : order === 'descending' ? 'DESC' : ''
  currentPage.value = 1
  fetchData()
}

function handleSelectionChange(val) {
  selectedRows.value = val
}

function startEdit(row) {
  editingId.value = row.id
}

async function saveEdit(row) {
  const url = props.type === 'expense' ? `/api/records/${row.id}` : `/api/income/${row.id}`
  await api.put(url, row)
  editingId.value = null
  await fetchData()
  categoryStore.bumpRefresh()
}

function cancelEdit() {
  editingId.value = null
  fetchData()
}

async function deleteSelected() {
  const toDelete = [...selectedRows.value]
  const deletedIds = new Set(toDelete.map(r => r.id))
  await Promise.all(
    toDelete.map(r => {
      const url = props.type === 'expense' ? `/api/records/${r.id}` : `/api/income/${r.id}`
      return api.delete(url)
    })
  )
  records.value = records.value.filter(r => !deletedIds.has(r.id))
  totalRecords.value = Math.max(0, totalRecords.value - toDelete.length)
  selectedRows.value = []
  categoryStore.bumpRefresh()
}

function applyFilter() {
  currentPage.value = 1
  fetchData()
}

async function fetchData() {
  try {
    const params = { page: currentPage.value, limit: pageSize }
    if (sortBy.value) params.sort_by = sortBy.value
    if (sortOrder.value) params.sort_order = sortOrder.value
    if (filterCategory.value) params.category = filterCategory.value

    // 统一处理日期范围：窄屏用独立字段，桌面用 dateRange
    const sd = isNarrow.value ? startDate.value : (dateRange.value && dateRange.value[0])
    const ed = isNarrow.value ? endDate.value   : (dateRange.value && dateRange.value[1])
    if (sd) params.start_date = sd
    if (ed) params.end_date = ed

    // 分类列表从 store 取（缓存复用），记录表仍需每次独立请求
    const [recRes] = await Promise.all([
      api.get(props.type === 'expense' ? '/api/records' : '/api/income', { params }),
      categoryStore.fetchCategories(props.type),
    ])
    records.value = recRes.data.data
    totalRecords.value = recRes.data.total
  } catch (err) {
    console.error('❌ 记录加载失败：', err)
  }
}

onMounted(fetchData)
let debounceTimer = null
watch(refreshCounter, () => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    currentPage.value = 1
    // 刷新信号发生时，强制从后端重新拉取分类，保证列表最新
    categoryStore.invalidate(props.type)
    fetchData()
  }, 100)
})
</script>

<style scoped>
.record-table-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 筛选工具栏 */
.table-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 14px;
  background: var(--color-bg);
  border-radius: 8px;
}
.filter-form {
  flex: 1;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
}
.filter-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* 金额色彩 */
.amount-expense { color: #ef4444; font-weight: 600; }
.amount-income  { color: #22c55e; font-weight: 600; }

/* 分类标签 */
.cat-tag {
  background: var(--color-primary-light) !important;
  color: var(--color-primary) !important;
  border-color: transparent !important;
  font-weight: 500;
}
.anomaly-tag {
  margin-left: 6px;
  font-size: 11px;
  vertical-align: middle;
}

/* 表格 */
.record-table :deep(.el-table__body-wrapper) { overflow-x: auto; }
.record-table :deep(th.el-table__cell) {
  background: var(--color-surface-2) !important;
  color: var(--color-text-muted);
  font-weight: 600;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

/* 可触摸行点击反馈 */
.record-table :deep(.touch-tappable-row) { cursor: pointer; }
.record-table :deep(.touch-tappable-row:active td) {
  background: var(--color-primary-light) !important;
  transition: background 0.12s;
}

/* 桌面端分页 */
.table-pagination {
  justify-content: flex-end;
  padding: 4px 0;
}

/* 移动端分页 */
.mobile-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 4px 0;
  flex-wrap: wrap;
}
.page-total-hint {
  font-size: 13px;
  color: var(--color-text-muted);
  white-space: nowrap;
}

/* 移动端布局 */
@media (max-width: 768px) {
  .table-toolbar {
    flex-direction: column;
    align-items: stretch;
  }
  .filter-form {
    flex-direction: column;
    align-items: stretch;
  }
  .filter-form :deep(.el-form-item) {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    margin-right: 0;
    margin-bottom: 8px;
    width: 100%;
  }
  .filter-form :deep(.el-form-item__content) {
    margin-left: 0 !important;
    width: 100%;
  }
  .filter-form :deep(.el-select),
  .filter-form :deep(.el-date-editor) {
    width: 100% !important;
    max-width: 100%;
  }
  .filter-actions {
    width: 100%;
  }
  .filter-actions .el-button {
    flex: 1;
  }
}

/* 行详情 / 编辑抽屉 */
:deep(.row-detail-drawer) {
  border-radius: 16px 16px 0 0 !important;
  box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.12) !important;
}
:deep(.row-detail-drawer .el-drawer__body) {
  padding: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.drawer-handle-bar {
  width: 36px;
  height: 4px;
  background: #d1d5db;
  border-radius: 2px;
  margin: 10px auto 0;
  flex-shrink: 0;
}

/* VIEW 模式：只读字段 */
.drawer-detail-body {
  padding: 8px 24px 12px;
  display: flex;
  flex-direction: column;
  flex: 1;
}
.drawer-detail-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 13px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.drawer-detail-row:last-child { border-bottom: none; }
.drawer-detail-label {
  font-size: 13px;
  color: var(--color-text-muted);
  font-weight: 500;
}
.drawer-detail-value {
  font-size: 15px;
  font-weight: 600;
  max-width: 65%;
  text-align: right;
  word-break: break-all;
}
.drawer-detail-value.text-normal { font-weight: 400; color: var(--color-text); }
.drawer-detail-value.text-muted  { font-weight: 400; color: var(--color-text-muted); }

/* EDIT 模式：表单 */
.drawer-edit-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
  padding: 14px 24px 6px;
  flex-shrink: 0;
}
.drawer-edit-form {
  padding: 4px 24px 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  flex: 1;
  overflow-y: auto;
}
.drawer-edit-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.drawer-edit-label {
  font-size: 12px;
  color: var(--color-text-muted);
  font-weight: 500;
}

/* 抽屉底部按钮区（view 和 edit 共用） */
.drawer-footer {
  display: flex;
  gap: 10px;
  padding: 14px 24px 28px;
  border-top: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}
.drawer-action-btn { flex: 1; }
</style>
