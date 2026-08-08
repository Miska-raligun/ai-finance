<template>
  <div class="recurring-wrap">
    <div class="recurring-head">
      <div class="recurring-hint">
        每月固定支出 / 收入（如房租、订阅、工资）可在这里登记一次，每月自动生成记录。
      </div>
      <el-button type="primary" size="small" @click="openCreate">＋ 新建规则</el-button>
    </div>

    <!-- 桌面：表格 -->
    <el-table
      v-if="!isMobile"
      :data="rules"
      size="small"
      empty-text="还没有定期规则"
      style="width: 100%"
    >
      <el-table-column label="类型" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="row.kind === 'income' ? 'success' : 'warning'" effect="plain">
            {{ row.kind === 'income' ? '收入' : '支出' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="分类" min-width="120" />
      <el-table-column label="金额" width="110" align="right">
        <template #default="{ row }">¥{{ row.amount.toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="频率" width="120" align="center">
        <template #default="{ row }">{{ freqText(row) }}</template>
      </el-table-column>
      <el-table-column prop="note" label="备注" min-width="160">
        <template #default="{ row }">{{ row.note || '—' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-switch :model-value="!!row.active" @change="toggleActive(row, $event)" />
        </template>
      </el-table-column>
      <el-table-column label="上次执行" width="120">
        <template #default="{ row }">
          <span class="text-muted">{{ row.last_run_date || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="130" align="right">
        <template #default="{ row }">
          <el-button size="small" link @click="openEdit(row)">编辑</el-button>
          <el-button size="small" link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 移动端：卡片列表 -->
    <div v-else class="recurring-mobile-list">
      <div v-if="!rules.length" class="empty">还没有定期规则</div>
      <div v-for="row in rules" :key="row.id" class="rc-card">
        <div class="rc-head">
          <el-tag size="small" :type="row.kind === 'income' ? 'success' : 'warning'" effect="plain">
            {{ row.kind === 'income' ? '收入' : '支出' }}
          </el-tag>
          <span class="rc-cat">{{ row.category }}</span>
          <span class="rc-amount">¥{{ row.amount.toFixed(2) }}</span>
        </div>
        <div class="rc-meta">
          <span>{{ freqText(row) }}</span>
          <span v-if="row.last_run_date">· 上次 {{ row.last_run_date }}</span>
        </div>
        <div v-if="row.note" class="rc-note">{{ row.note }}</div>
        <div class="rc-actions">
          <el-switch :model-value="!!row.active" @change="toggleActive(row, $event)" />
          <el-button size="small" link @click="openEdit(row)">编辑</el-button>
          <el-button size="small" link type="danger" @click="remove(row)">删除</el-button>
        </div>
      </div>
    </div>

    <div class="recurring-footer">
      <el-button size="small" :loading="runningNow" @click="runNow">▶︎ 立即检查并补单</el-button>
      <span class="text-muted run-hint">只展开"本月已到日、还没跑过"的规则；定时由 cron 调用。</span>
    </div>

    <!-- 编辑 / 新建对话框 -->
    <el-dialog
      v-model="showDialog"
      :title="editing.id ? '编辑规则' : '新建规则'"
      :width="dialogWidth"
      append-to-body
    >
      <el-form label-width="80px">
        <el-form-item label="类型">
          <el-radio-group v-model="editing.kind">
            <el-radio value="expense">支出</el-radio>
            <el-radio value="income">收入</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="editing.category" placeholder="如：房租 / 工资 / 订阅" />
        </el-form-item>
        <el-form-item label="金额">
          <el-input-number
            v-model="editing.amount"
            :min="0.01" :step="100" :precision="2"
            controls-position="right" style="width:100%"
          />
        </el-form-item>
        <el-form-item label="频率">
          <el-radio-group v-model="editing.freq">
            <el-radio-button label="monthly">每月</el-radio-button>
            <el-radio-button label="weekly">每周</el-radio-button>
            <el-radio-button label="yearly">每年</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="editing.freq === 'weekly'" label="星期">
          <el-select v-model="editing.day_of_week" style="width:100%">
            <el-option v-for="(w, i) in WEEKDAYS" :key="i" :label="w" :value="i" />
          </el-select>
        </el-form-item>

        <template v-else>
          <el-form-item v-if="editing.freq === 'yearly'" label="月份">
            <el-select v-model="editing.month_of_year" style="width:100%">
              <el-option v-for="m in 12" :key="m" :label="`${m} 月`" :value="m" />
            </el-select>
          </el-form-item>
          <el-form-item :label="editing.freq === 'yearly' ? '日' : '每月'">
            <el-input-number
              v-model="editing.day_of_month"
              :min="1" :max="31" :step="1"
              controls-position="right" style="width:100%"
            />
            <div class="form-hint">月不足该日时（如 2 月 31 日）自动回退到月末</div>
          </el-form-item>
        </template>
        <el-form-item label="备注">
          <el-input v-model="editing.note" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'

const rules = ref([])
const showDialog = ref(false)
const saving = ref(false)
const runningNow = ref(false)
const editing = ref({})

const _mq = window.matchMedia('(max-width: 768px)')
const isMobile = ref(_mq.matches)
function _onMq(e) { isMobile.value = e.matches }
onMounted(() => _mq.addEventListener('change', _onMq))
onBeforeUnmount(() => _mq.removeEventListener('change', _onMq))

// 弹窗宽度：桌面 420px 固定；移动端用视口宽减边距，避免 420px 在 360px
// 屏上溢出/被切。
const dialogWidth = computed(() => isMobile.value ? 'calc(100vw - 32px)' : '420px')

async function load() {
  const res = await api.get('/api/recurring')
  rules.value = res.data || []
}
onMounted(load)

const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

function freqText(row) {
  if (row.freq === 'weekly') return `每周${WEEKDAYS[row.day_of_week] || '?'}`
  if (row.freq === 'yearly') return `每年 ${row.month_of_year || '?'}月${row.day_of_month}日`
  return `每月 ${row.day_of_month} 日`
}

function openCreate() {
  editing.value = {
    id: null, kind: 'expense', category: '', amount: 0,
    freq: 'monthly', day_of_month: 1, day_of_week: 0, month_of_year: 1, note: '',
  }
  showDialog.value = true
}
function openEdit(row) {
  editing.value = {
    freq: 'monthly', day_of_week: 0, month_of_year: 1, ...row,
  }
  showDialog.value = true
}

function _freqPayload(r) {
  const p = { kind: r.kind, category: r.category, amount: Number(r.amount),
              note: r.note, freq: r.freq }
  if (r.freq === 'weekly') p.day_of_week = Number(r.day_of_week)
  else {
    p.day_of_month = Number(r.day_of_month)
    if (r.freq === 'yearly') p.month_of_year = Number(r.month_of_year)
  }
  return p
}

async function save() {
  const r = editing.value
  if (!r.category) { ElMessage.warning('请填写分类'); return }
  if (!(Number(r.amount) > 0)) { ElMessage.warning('金额必须 > 0'); return }
  saving.value = true
  try {
    if (r.id) {
      await api.patch(`/api/recurring/${r.id}`, _freqPayload(r))
    } else {
      await api.post('/api/recurring', _freqPayload(r))
    }
    ElMessage.success('已保存')
    showDialog.value = false
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || '保存失败')
  } finally {
    saving.value = false
  }
}

async function toggleActive(row, next) {
  try {
    await api.patch(`/api/recurring/${row.id}`, { active: next })
    row.active = next ? 1 : 0
  } catch (e) {
    ElMessage.error('切换状态失败')
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`删除规则「${row.category}」？已展开的历史记录不会被删除。`,
      '确认删除', { type: 'warning' })
    await api.delete(`/api/recurring/${row.id}`)
    ElMessage.success('已删除')
    await load()
  } catch { /* 取消 */ }
}

async function runNow() {
  runningNow.value = true
  try {
    const res = await api.post('/api/recurring/run-now')
    const { executed, errors } = res.data
    if (executed > 0) {
      ElMessage.success(`已展开 ${executed} 条规则`)
      await load()
    } else if (errors && errors.length) {
      ElMessage.warning('部分规则展开失败，详见日志')
    } else {
      ElMessage.info('当前没有规则需要展开（本月已跑过或还没到日）')
    }
  } catch (e) {
    ElMessage.error('调用失败')
  } finally {
    runningNow.value = false
  }
}
</script>

<style scoped>
.recurring-wrap { display: flex; flex-direction: column; gap: 14px; }
.recurring-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.recurring-hint {
  font-size: 12px;
  color: var(--color-text-muted);
  max-width: 560px;
  line-height: 1.6;
}
.form-hint { font-size: 11px; color: var(--color-text-muted); margin-top: 2px; }
.text-muted { color: var(--color-text-muted); }
.recurring-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding-top: 6px;
}
.run-hint { font-size: 11px; }

/* 移动端卡片 */
.recurring-mobile-list { display: flex; flex-direction: column; gap: 10px; }
.empty { text-align: center; padding: 28px 0; color: var(--color-text-muted); font-size: 13px; }
.rc-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.rc-head { display: flex; align-items: center; gap: 8px; }
.rc-cat { font-weight: 600; flex: 1; min-width: 0; }
.rc-amount { font-weight: 700; color: var(--color-primary); font-variant-numeric: tabular-nums; }
.rc-meta { font-size: 12px; color: var(--color-text-muted); }
.rc-note { font-size: 12px; color: var(--color-text); }
.rc-actions { display: flex; align-items: center; gap: 8px; justify-content: flex-end; }

@media (max-width: 768px) {
  .recurring-head { flex-direction: column; align-items: stretch; }
}
</style>
