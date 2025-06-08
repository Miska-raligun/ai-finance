<template>
  <el-card>
    <template #header>📋 记账记录表格</template>

    <el-form :inline="true" size="small" style="margin-bottom: 10px">
      <el-form-item label="类型">
        <el-select v-model="filterCategory" placeholder="全部" clearable style="width: 100px">
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
        />
      </el-form-item>

      <el-button type="primary" @click="applyFilter">筛选</el-button>
      <el-button plain @click="resetFilters">显示全部</el-button>
    </el-form>

    <el-table
      :data="paginatedData"
      stripe
      border
      style="width: 100%"
      :default-sort="{ prop: 'date', order: 'descending' }"
    >
      <el-table-column prop="category" label="类型" />
      <el-table-column prop="note" label="备注" />
      <el-table-column prop="date" label="时间" sortable />
      <el-table-column prop="amount" label="金额" sortable />
      <el-table-column prop="left_budget" label="剩余预算" sortable />
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
import { ref, onMounted, watch, computed } from 'vue'
import axios from 'axios'

const props = defineProps({ refreshFlag: Number })

const records = ref([])
const filtered = ref([])
const categories = ref([])
const filterCategory = ref('')
const dateRange = ref([])

const pageSize = 10
const currentPage = ref(1)

const paginatedData = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  const end = start + pageSize
  return filtered.value.slice(start, end)
})

function handlePageChange(val) {
  currentPage.value = val
}

function resetFilters() {
  filterCategory.value = ''
  dateRange.value = []
  applyFilter()
}

function applyFilter() {
  filtered.value = records.value.filter(r => {
    const matchCategory = filterCategory.value
      ? r.category === filterCategory.value
      : true
    const matchDate = dateRange.value.length
      ? r.date >= dateRange.value[0] && r.date <= dateRange.value[1]
      : true
    return matchCategory && matchDate
  })
  currentPage.value = 1
}

async function fetchRecords() {
  const [recRes, catRes, budgetRes] = await Promise.all([
    axios.get('/records'),
    axios.get('/categories'),
    axios.get('/budgets')
  ])
  const rec = recRes.data
  const cats = catRes.data.map(c => c.name)
  const budgetMap = {}
  for (const b of budgetRes.data) {
    budgetMap[b.category] = b.amount
  }

  for (const r of rec) {
    const used = rec
      .filter(x => x.category === r.category && x.date <= r.date)
      .reduce((sum, x) => sum + x.amount, 0)
    r.left_budget = budgetMap[r.category]
      ? (budgetMap[r.category] - used).toFixed(2)
      : '—'
  }

  records.value = rec
  categories.value = cats
  applyFilter()
}

onMounted(fetchRecords)
watch(() => props.refreshFlag, fetchRecords)
</script>


