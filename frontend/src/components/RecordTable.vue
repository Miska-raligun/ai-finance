<!-- components/RecordTable.vue -->
<template>
  <el-card>
    <template #header>{{ title }}</template>

    <el-form :inline="true" size="small" style="margin-bottom: 10px; display: flex; align-items: center; gap: 10px">
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
        />
      </el-form-item>

      <el-button type="primary" size="small" @click="applyFilter">筛选</el-button>
      <el-button plain size="small" @click="resetFilters">显示全部</el-button>
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
      <el-table-column prop="amount" :label="showBudget ? '支出金额' : '收入金额'" sortable />
      <el-table-column v-if="showBudget" prop="left_budget" label="剩余预算" sortable />
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
import axios from 'axios'

const props = defineProps({
  type: { type: String, default: 'expense' }, // 'expense' or 'income'
  refreshFlag: Number,
  title: { type: String, default: '📋 记录表格' },
  showBudget: { type: Boolean, default: true }
})

const records = ref([])
const filtered = ref([])
const categories = ref([])
const filterCategory = ref('')
const dateRange = ref([])

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
      axios.get(props.type === 'expense' ? '/records' : '/income'),
      axios.get('/categories', {
        params: {
          type: props.type === 'expense' ? 'expense' : 'income'
        }
      })
    ])

    const rec = recRes.data
    const cats = catRes.data.map(c => c.name)
    categories.value = cats
    console.log("📋 收入数据：", rec)
    console.log("📂 分类数据：", cats)
    if (props.type === 'expense') {
      const budgets = (await axios.get('/budgets')).data
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


onMounted(fetchData)
watch(() => props.refreshFlag, fetchData)
</script>



