<!-- components/TransactionLog.vue — 资产交易流水:查看 + 录入(买/卖/分红/调整) -->
<template>
  <div class="txn-log">
    <div class="txn-header">
      <span class="txn-title">📜 交易流水</span>
      <el-button size="small" type="primary" :disabled="!assets.length" @click="openAdd">
        + 记一笔
      </el-button>
    </div>

    <el-empty v-if="!loading && rows.length === 0" description="还没有交易流水，卖出资产会自动记一笔，也可手动录入买入/分红" />

    <el-table v-else v-loading="loading" :data="rows" size="small" class="txn-table">
      <el-table-column prop="date" label="日期" width="110" />
      <el-table-column prop="asset_name" label="资产" min-width="100" show-overflow-tooltip />
      <el-table-column label="类型" width="72">
        <template #default="{ row }">
          <el-tag size="small" :type="KIND_TAG[row.kind] || 'info'">{{ KIND_LABEL[row.kind] || row.kind }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="数量" width="90" align="right">
        <template #default="{ row }">{{ fmtNum(row.quantity) }}</template>
      </el-table-column>
      <el-table-column label="价格" width="100" align="right">
        <template #default="{ row }">¥{{ fmtNum(row.price) }}</template>
      </el-table-column>
      <el-table-column label="金额" width="110" align="right">
        <template #default="{ row }">¥{{ fmtMoney(row.quantity * row.price + (row.fee || 0)) }}</template>
      </el-table-column>
      <el-table-column prop="note" label="备注" min-width="120" show-overflow-tooltip />
    </el-table>

    <el-dialog v-model="showAdd" title="记一笔交易" :width="dialogWidth">
      <el-form label-width="72px" size="small">
        <el-form-item label="资产">
          <el-select v-model="form.asset_id" placeholder="选择资产" style="width:100%">
            <el-option v-for="a in assets" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="form.kind">
            <el-radio-button v-for="k in KINDS" :key="k" :label="k">{{ KIND_LABEL[k] }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="form.quantity" :min="0" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="价格">
          <el-input-number v-model="form.price" :min="0" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="费用">
          <el-input-number v-model="form.fee" :min="0" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="form.date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdd = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

const props = defineProps({
  assets: { type: Array, default: () => [] },
})

const KINDS = ['buy', 'sell', 'dividend', 'adjust']
const KIND_LABEL = { buy: '买入', sell: '卖出', dividend: '分红', adjust: '调整' }
const KIND_TAG = { buy: 'success', sell: 'danger', dividend: 'warning', adjust: 'info' }

const rows = ref([])
const loading = ref(false)
const showAdd = ref(false)
const saving = ref(false)
const dialogWidth = computed(() => window.innerWidth < 768 ? 'calc(100vw - 28px)' : '440px')

const today = new Date().toISOString().slice(0, 10)
const form = reactive({ asset_id: null, kind: 'buy', quantity: 0, price: 0, fee: 0, date: today, note: '' })

function fmtNum(n) {
  const v = Number(n) || 0
  return Number.isInteger(v) ? String(v) : v.toFixed(4).replace(/\.?0+$/, '')
}
function fmtMoney(n) {
  return (Number(n) || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function load() {
  loading.value = true
  try {
    const res = await api.get('/api/investment/transactions')
    rows.value = res.data || []
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

function openAdd() {
  Object.assign(form, { asset_id: props.assets[0]?.id ?? null, kind: 'buy', quantity: 0, price: 0, fee: 0, date: today, note: '' })
  showAdd.value = true
}

async function submit() {
  if (!form.asset_id) { ElMessage.warning('请选择资产'); return }
  if (form.quantity <= 0 || form.price <= 0) { ElMessage.warning('数量和价格需大于 0'); return }
  saving.value = true
  try {
    await api.post('/api/investment/transactions', { ...form })
    ElMessage.success('已记录')
    showAdd.value = false
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || '保存失败')
  } finally {
    saving.value = false
  }
}

defineExpose({ load })
onMounted(load)
</script>

<style scoped>
.txn-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.txn-title { font-size: 15px; font-weight: 800; color: var(--color-text-strong); }
.txn-table { width: 100%; }
</style>
