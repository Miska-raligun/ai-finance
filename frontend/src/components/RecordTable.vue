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
      <el-table-column v-if="showDateColumn" prop="date" label="日期" sortable min-width="100">
        <template #default="scope">
          <template v-if="editingId === scope.row.id">
            <el-date-picker v-model="scope.row.date" type="date" value-format="YYYY-MM-DD" style="width:130px" />
          </template>
          <template v-else>{{ scope.row.date }}</template>
        </template>
      </el-table-column>
      <el-table-column prop="amount" :label="showBudget ? '支出金额' : '收入金额'" sortable min-width="90">
        <template #default="scope">
          <template v-if="editingId === scope.row.id">
            <el-input-number v-model="scope.row.amount" :min="0" style="width:120px" />
          </template>
          <template v-else>
            <span :class="showBudget ? 'amount-expense' : 'amount-income'">
              ¥{{ scope.row.amount }}
            </span>
          </template>
        </template>
      </el-table-column>
      <el-table-column v-if="showBudget && !isNarrow" prop="left_budget" label="剩余预算" sortable min-width="90">
        <template #default="scope">
          <span v-if="scope.row.left_budget === '—'" style="color: var(--color-text-muted)">—</span>
          <span v-else :class="scope.row.left_budget < 0 ? 'amount-expense' : 'amount-income'">
            {{ scope.row.left_budget < 0 ? `-¥${Math.abs(scope.row.left_budget)}` : `¥${scope.row.left_budget}` }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="130" :fixed="isNarrow ? false : 'right'">
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

    <!-- 触摸行详情抽屉（手机+平板） -->
    <el-drawer
      v-model="showPopover"
      direction="btt"
      :with-header="false"
      :size="showBudget ? '300px' : '252px'"
      class="row-detail-drawer"
    >
      <div class="drawer-handle-bar"></div>
      <div v-if="popoverRow" class="drawer-detail-body">
        <div class="drawer-detail-row">
          <span class="drawer-detail-label">分类</span>
          <el-tag size="small" type="info" class="cat-tag">{{ popoverRow.category }}</el-tag>
        </div>
        <div class="drawer-detail-row">
          <span class="drawer-detail-label">金额</span>
          <span :class="showBudget ? 'drawer-detail-value amount-expense' : 'drawer-detail-value amount-income'">
            ¥{{ popoverRow.amount }}
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
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import api from '@/api'

const props = defineProps({
  type: { type: String, default: 'expense' },
  refreshFlag: Number,
  title: { type: String, default: '记录表格' },
  showBudget: { type: Boolean, default: true }
})
const emit = defineEmits(['refresh'])

const records = ref([])
const totalRecords = ref(0)
const categories = ref([])
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

// 触摸行详情
const popoverRow = ref(null)
const showPopover = ref(false)

function handleRowClick(row, column, event) {
  if (editingId.value !== null) return
  if (event.target.closest('.el-button, button, input, .el-select, .el-input, .el-date-editor')) return
  popoverRow.value = row
  showPopover.value = true
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
  emit('refresh')
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
  emit('refresh')
}

function applyFilter() {
  currentPage.value = 1
  fetchData()
}

async function fetchData() {
  try {
    const params = { page: currentPage.value, limit: pageSize }
    if (filterCategory.value) params.category = filterCategory.value

    // 统一处理日期范围：窄屏用独立字段，桌面用 dateRange
    const sd = isNarrow.value ? startDate.value : (dateRange.value && dateRange.value[0])
    const ed = isNarrow.value ? endDate.value   : (dateRange.value && dateRange.value[1])
    if (sd) params.start_date = sd
    if (ed) params.end_date = ed

    const [recRes, catRes] = await Promise.all([
      api.get(props.type === 'expense' ? '/api/records' : '/api/income', { params }),
      api.get('/api/categories', { params: { type: props.type === 'expense' ? 'expense' : 'income' } })
    ])
    records.value = recRes.data.data
    totalRecords.value = recRes.data.total
    categories.value = catRes.data.map(c => c.name)
  } catch (err) {
    console.error('❌ 记录加载失败：', err)
  }
}

onMounted(fetchData)
let debounceTimer = null
watch(() => props.refreshFlag, () => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    currentPage.value = 1
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

/* 表格 */
.record-table :deep(.el-table__body-wrapper) { overflow-x: auto; }
.record-table :deep(th.el-table__cell) {
  background: #F8FAFC !important;
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

/* 触摸详情抽屉 */
:deep(.row-detail-drawer) {
  border-radius: 16px 16px 0 0 !important;
  box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.12) !important;
}
:deep(.row-detail-drawer .el-drawer__body) {
  padding: 0;
  overflow: hidden;
}

.drawer-handle-bar {
  width: 36px;
  height: 4px;
  background: #d1d5db;
  border-radius: 2px;
  margin: 10px auto 0;
}

.drawer-detail-body {
  padding: 16px 24px 20px;
  display: flex;
  flex-direction: column;
  gap: 0;
}
.drawer-detail-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 0;
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
</style>
