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
        <template v-if="!isMobile">
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
      <el-table-column v-if="!isMobile" prop="note" label="备注" min-width="90">
        <template #default="scope">
          <template v-if="editingId === scope.row.id">
            <el-input v-model="scope.row.note" size="small" />
          </template>
          <template v-else>{{ scope.row.note }}</template>
        </template>
      </el-table-column>
      <el-table-column prop="date" label="日期" sortable min-width="100">
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
      <el-table-column v-if="showBudget && !isMobile" prop="left_budget" label="剩余预算" sortable min-width="90">
        <template #default="scope">
          <span v-if="scope.row.left_budget === '—'" style="color: var(--color-text-muted)">—</span>
          <span v-else :class="scope.row.left_budget < 0 ? 'amount-expense' : 'amount-income'">
            {{ scope.row.left_budget < 0 ? `-¥${Math.abs(scope.row.left_budget)}` : `¥${scope.row.left_budget}` }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="130" :fixed="isMobile ? false : 'right'">
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
      v-if="!isMobile"
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

// 移动端检测
const isMobile = ref(window.innerWidth < 768)
function onResize() {
  isMobile.value = window.innerWidth < 768
}
onMounted(() => window.addEventListener('resize', onResize))
onUnmounted(() => window.removeEventListener('resize', onResize))

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
  for (const r of selectedRows.value) {
    const url = props.type === 'expense' ? `/api/records/${r.id}` : `/api/income/${r.id}`
    await api.delete(url)
  }
  selectedRows.value = []
  await fetchData()
  emit('refresh')
}

function applyFilter() {
  currentPage.value = 1
  fetchData()
}

async function fetchData() {
  try {
    records.value = []
    totalRecords.value = 0
    const params = { page: currentPage.value, limit: pageSize }
    if (filterCategory.value) params.category = filterCategory.value

    // 统一处理日期范围：桌面用 dateRange，移动用独立字段
    const sd = isMobile.value ? startDate.value : (dateRange.value && dateRange.value[0])
    const ed = isMobile.value ? endDate.value   : (dateRange.value && dateRange.value[1])
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
</style>
