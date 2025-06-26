<!-- components/RecordTable.vue -->
<template>
  <el-card>
    <template #header>{{ title }}</template>

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

      <el-form-item label="时间范围">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          start-placeholder="开始"
          end-placeholder="结束"
          value-format="YYYY-MM-DD"
          style="width: 100%"
        />
      </el-form-item>

      <el-button type="primary" size="small" @click="applyFilter">筛选</el-button>
      <el-button plain size="small" @click="resetFilters">显示全部</el-button>
      <el-button type="danger" size="small" @click="deleteSelected" :disabled="!selectedRows.length">删除所选</el-button>
    </el-form>

    <el-table
      :data="paginatedData"
      stripe
      border
      style="width: 100%"
      @selection-change="handleSelectionChange"
    >
      <el-table-column type="selection" width="55" />
      <el-table-column prop="category" label="类型">
        <template #default="scope">
          <template v-if="editingId === scope.row.id">
            <el-select v-model="scope.row.category" style="width: 100px">
              <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
            </el-select>
          </template>
          <template v-else>{{ scope.row.category }}</template>
        </template>
      </el-table-column>
      <el-table-column prop="note" label="备注">
        <template #default="scope">
          <template v-if="editingId === scope.row.id">
            <el-input v-model="scope.row.note" size="small" />
          </template>
          <template v-else>{{ scope.row.note }}</template>
        </template>
      </el-table-column>
      <el-table-column prop="date" label="时间" sortable>
        <template #default="scope">
          <template v-if="editingId === scope.row.id">
            <el-date-picker v-model="scope.row.date" type="date" value-format="YYYY-MM-DD" />
          </template>
          <template v-else>{{ scope.row.date }}</template>
        </template>
      </el-table-column>
      <el-table-column prop="amount" :label="showBudget ? '支出金额' : '收入金额'" sortable>
        <template #default="scope">
          <template v-if="editingId === scope.row.id">
            <el-input-number v-model="scope.row.amount" :min="0" />
          </template>
          <template v-else>{{ Number(scope.row.amount).toFixed(2) }}</template>
        </template>
      </el-table-column>
      <el-table-column v-if="showBudget" prop="left_budget" label="剩余预算" sortable />
      <el-table-column label="操作" width="150">
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

    <el-pagination
      background
      layout="prev, pager, next, total"
      :total="filtered.length"
      :page-size="pageSize"
      :current-page="currentPage"
      @current-change="handlePageChange"
      style="margin-top: 15px; text-align: right"
    />
  </el-card>
</template>

<script setup>
import { ref, watch, onMounted, computed } from 'vue'
import api from '@/api'

const props = defineProps({
  type: { type: String, default: 'expense' }, // 'expense' or 'income'
  refreshFlag: Number,
  title: { type: String, default: '📋 记录表格' },
  showBudget: { type: Boolean, default: true }
})
const emit = defineEmits(['refresh'])

const records = ref([])
const filtered = ref([])
const categories = ref([])
const filterCategory = ref('')
const dateRange = ref([])
const today = new Date().toISOString().slice(0, 10)
const selectedRows = ref([])
const editingId = ref(null)
const pageSize = 10
const currentPage = ref(1)

const paginatedData = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return filtered.value.slice(start, start + pageSize)
})

function handlePageChange(val) {
  currentPage.value = val
}

function resetFilters() {
  filterCategory.value = ''
  dateRange.value = []
  applyFilter()
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
  filtered.value = records.value.filter(r => {
    const matchCategory = filterCategory.value ? r.category === filterCategory.value : true
    const matchDate = dateRange.value.length
      ? r.date >= dateRange.value[0] && r.date <= dateRange.value[1]
      : true
    return matchCategory && matchDate
  })
  currentPage.value = 1
}

async function fetchData() {
  try {
    const [recRes, catRes] = await Promise.all([
      api.get(props.type === 'expense' ? '/api/records' : '/api/income'),
      api.get('/api/categories', {
        params: {
          type: props.type === 'expense' ? 'expense' : 'income'
        }
      })
    ])

    const rec = recRes.data
      .slice()
      .sort((a, b) => {
        const d1 = new Date(a.date).getTime()
        const d2 = new Date(b.date).getTime()
        if (d1 === d2) return b.id - a.id
        return d2 - d1
      })
    const cats = catRes.data.map(c => c.name)
    categories.value = cats
    //console.log("📋 收入数据：", rec)
    //console.log("📂 分类数据：", cats)
    if (props.type === 'expense') {
      const budgets = (await api.get('/api/budgets')).data
      const budgetMap = {}
      for (const b of budgets) {
        budgetMap[b.category + '_' + b.month] = b.amount
      }

      for (const r of rec) {
        r.month = r.date.slice(0, 7)
        const used = rec
          .filter(x => x.category === r.category && x.date.slice(0, 7) === r.month && x.date <= r.date)
          .reduce((sum, x) => sum + x.amount, 0)
        const key = r.category + '_' + r.month
        r.left_budget = budgetMap[key] ? (budgetMap[key] - used).toFixed(2) : '—'
      }
    }

    records.value = rec
    applyFilter()
  } catch (err) {
    console.error("❌ 记录加载失败：", err)
  }
}


onMounted(() => {
  dateRange.value = [today, today]
  fetchData()
})
watch(() => props.refreshFlag, fetchData)
</script>

<style scoped>
.filter-form {
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
@media (max-width: 600px) {
  .filter-form {
    flex-direction: column;
    align-items: flex-start;
    overflow-x: auto;
    flex-wrap: wrap; /* 允许换行 */
  }

  .filter-form .el-form-item {
    width: 100%;
  }

  .filter-form .el-date-editor {
    width: 100%;
  }

  .filter-form .el-button {
    width: auto;
    margin-right: 8px; /* 可选，增加间隔 */
  }
}
</style>



