<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <span>📁 我的资产</span>
        <el-button size="small" type="primary" @click="openCreate">新增资产</el-button>
      </div>
    </template>

    <el-table
      :data="assets"
      size="small"
      empty-text="还没有录入资产"
      style="width: 100%"
    >
      <el-table-column prop="name" label="名称" min-width="120" />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">{{ TYPE_LABEL[row.type] || row.type }}</template>
      </el-table-column>
      <el-table-column prop="symbol" label="代码" width="100" />
      <el-table-column prop="holdings" label="数量" width="100" align="right">
        <template #default="{ row }">{{ row.holdings || '—' }}</template>
      </el-table-column>
      <el-table-column prop="cost_basis" label="成本" width="110" align="right">
        <template #default="{ row }">¥{{ (row.cost_basis || 0).toFixed(2) }}</template>
      </el-table-column>
      <el-table-column prop="current_value" label="现值" width="110" align="right">
        <template #default="{ row }">¥{{ (row.current_value || 0).toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="盈亏" width="110" align="right">
        <template #default="{ row }">
          <span :class="pnlClass(row)">{{ pnlStr(row) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button size="small" text @click="openEdit(row)">编辑</el-button>
          <el-button size="small" text type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showDialog" :title="editing ? '编辑资产' : '新增资产'" width="480px">
      <el-form label-width="90px">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="如：沪深300指数基金" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.type" style="width:100%">
            <el-option v-for="(label, key) in TYPE_LABEL" :key="key" :value="key" :label="label" />
          </el-select>
        </el-form-item>
        <el-form-item label="代码">
          <el-input v-model="form.symbol" placeholder="如：510300（可选）" />
        </el-form-item>
        <el-form-item label="持仓数量">
          <el-input-number v-model="form.holdings" :min="0" :step="1" controls-position="right" style="width:100%" />
        </el-form-item>
        <el-form-item label="总成本">
          <el-input-number v-model="form.cost_basis" :min="0" :step="100" controls-position="right" style="width:100%" />
        </el-form-item>
        <el-form-item label="当前市值">
          <el-input-number v-model="form.current_value" :min="0" :step="100" controls-position="right" style="width:100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useInvestmentStore } from '@/stores/investment'

const props = defineProps({ assets: { type: Array, default: () => [] } })
const store = useInvestmentStore()

const TYPE_LABEL = {
  stock: '股票', fund: '基金', bond: '债券', cash: '现金',
  crypto: '加密货币', realestate: '房地产', other: '其他',
}

const showDialog = ref(false)
const editing = ref(null)
const form = reactive({
  name: '', type: 'fund', symbol: '', holdings: 0,
  cost_basis: 0, current_value: 0, notes: '',
})

function reset() {
  form.name = ''; form.type = 'fund'; form.symbol = ''
  form.holdings = 0; form.cost_basis = 0; form.current_value = 0; form.notes = ''
  editing.value = null
}

function openCreate() { reset(); showDialog.value = true }

function openEdit(row) {
  editing.value = row
  Object.assign(form, {
    name: row.name, type: row.type, symbol: row.symbol || '',
    holdings: row.holdings || 0, cost_basis: row.cost_basis || 0,
    current_value: row.current_value || 0, notes: row.notes || '',
  })
  showDialog.value = true
}

async function save() {
  if (!form.name) {
    ElMessage.warning('请填写资产名称'); return
  }
  try {
    if (editing.value) {
      await store.updateAsset(editing.value.id, { ...form })
      ElMessage.success('已更新')
    } else {
      await store.createAsset({ ...form })
      ElMessage.success('已添加')
    }
    showDialog.value = false; reset()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '保存失败')
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确定删除「${row.name}」？相关交易流水也会一并删除。`,
      '确认删除', { type: 'warning' })
    await store.deleteAsset(row.id)
    ElMessage.success('已删除')
  } catch { /* 取消 */ }
}

function pnl(row) {
  const cost = row.cost_basis || 0
  const value = row.current_value || 0
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
</script>

<style scoped>
.header-row {
  display: flex; justify-content: space-between; align-items: center; width: 100%;
}
.up { color: #EF4444; font-weight: 600; }
.down { color: #22C55E; font-weight: 600; }
</style>
