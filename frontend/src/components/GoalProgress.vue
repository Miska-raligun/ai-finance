<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <span>🎯 理财目标</span>
        <el-button size="small" type="primary" @click="openCreate">新增目标</el-button>
      </div>
    </template>

    <div v-if="!sortedGoals.length" class="empty">
      还没有设置目标。设定一个短/中期目标，让攒钱更有动力～
    </div>

    <div v-else class="goals">
      <div
        v-for="g in sortedGoals"
        :key="g.id"
        class="goal-item"
        @click="openView(g)"
      >
        <div class="goal-head">
          <div class="goal-title">
            <span
              class="priority-badge"
              :class="priorityClass(g.priority)"
              :title="priorityHint(g.priority)"
            >{{ priorityLabel(g.priority) }}</span>
            <span class="goal-name">{{ g.name }}</span>
          </div>
          <span class="goal-amount">
            ¥{{ (g.current_progress || 0).toFixed(0) }} / ¥{{ g.target_amount.toFixed(0) }}
          </span>
        </div>
        <el-progress
          :percentage="pct(g)"
          :color="pctColor(pct(g))"
          :stroke-width="10"
        />
        <div class="goal-meta">
          <span v-if="g.deadline">截止 {{ g.deadline }}</span>
          <span v-else>未设截止日期</span>
          <span class="actions" @click.stop>
            <el-button size="small" text @click="openAdvise(g)">AI 方案</el-button>
          </span>
        </div>
      </div>
    </div>

    <!-- 查看 / 编辑抽屉，和资产表保持一致风格 -->
    <el-drawer
      v-model="showDrawer"
      direction="btt"
      :with-header="false"
      :size="drawerMode === 'edit' ? '520px' : '360px'"
      class="goal-drawer"
      @close="onDrawerClose"
    >
      <div class="drawer-handle-bar"></div>

      <template v-if="drawerMode === 'view' && popoverRow">
        <div class="drawer-body">
          <div class="drawer-row">
            <span class="drawer-label">名称</span>
            <span class="drawer-value">{{ popoverRow.name }}</span>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">优先级</span>
            <span class="drawer-value">
              <span class="priority-badge" :class="priorityClass(popoverRow.priority)">
                {{ priorityLabel(popoverRow.priority) }}
              </span>
              <small class="priority-meaning">{{ priorityHint(popoverRow.priority) }}</small>
            </span>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">目标金额</span>
            <span class="drawer-value">¥{{ popoverRow.target_amount.toFixed(2) }}</span>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">已完成</span>
            <span class="drawer-value">¥{{ (popoverRow.current_progress || 0).toFixed(2) }}</span>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">进度</span>
            <span class="drawer-value">{{ pct(popoverRow) }}%</span>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">截止日期</span>
            <span class="drawer-value text-normal">{{ popoverRow.deadline || '—' }}</span>
          </div>
          <div class="drawer-row">
            <span class="drawer-label">备注</span>
            <span class="drawer-value text-normal">{{ popoverRow.note || '—' }}</span>
          </div>
        </div>
        <div class="drawer-footer">
          <el-button class="drawer-action-btn" plain type="danger" @click="deleteFromDrawer">
            🗑️ 删除
          </el-button>
          <el-button class="drawer-action-btn" type="primary" @click="startEdit">
            ✏️ 编辑
          </el-button>
        </div>
      </template>

      <template v-if="drawerMode === 'edit' && editingRow">
        <div class="drawer-edit-title">{{ editingRow.id ? '编辑目标' : '新增目标' }}</div>
        <div class="drawer-edit-form">
          <div class="drawer-edit-field">
            <label class="drawer-edit-label">名称</label>
            <el-input v-model="editingRow.name" placeholder="如：买房首付" />
          </div>
          <div class="drawer-edit-field">
            <label class="drawer-edit-label">目标金额</label>
            <el-input-number
              v-model="editingRow.target_amount"
              :min="0" :step="1000" controls-position="right" style="width:100%"
            />
          </div>
          <div class="drawer-edit-field">
            <label class="drawer-edit-label">已完成</label>
            <el-input-number
              v-model="editingRow.current_progress"
              :min="0" :step="100" controls-position="right" style="width:100%"
            />
          </div>
          <div class="drawer-edit-field">
            <label class="drawer-edit-label">截止日期</label>
            <el-date-picker v-model="editingRow.deadline" type="date" value-format="YYYY-MM-DD" style="width:100%" />
          </div>
          <div class="drawer-edit-field">
            <label class="drawer-edit-label">优先级（影响 AI 方案推荐激进度）</label>
            <el-select v-model="editingRow.priority" style="width:100%">
              <el-option :value="1">
                <template #default>
                  <span class="priority-badge high">最高</span>
                  <span class="option-hint">最紧迫，建议采用激进档</span>
                </template>
              </el-option>
              <el-option :value="2">
                <template #default>
                  <span class="priority-badge high">高</span>
                  <span class="option-hint">比较重要，倾向激进档</span>
                </template>
              </el-option>
              <el-option :value="3">
                <template #default>
                  <span class="priority-badge mid">中</span>
                  <span class="option-hint">默认，推荐平衡档</span>
                </template>
              </el-option>
              <el-option :value="4">
                <template #default>
                  <span class="priority-badge low">低</span>
                  <span class="option-hint">可以慢慢攒</span>
                </template>
              </el-option>
              <el-option :value="5">
                <template #default>
                  <span class="priority-badge low">最低</span>
                  <span class="option-hint">不紧急，保守档即可</span>
                </template>
              </el-option>
            </el-select>
          </div>
          <div class="drawer-edit-field">
            <label class="drawer-edit-label">备注</label>
            <el-input v-model="editingRow.note" type="textarea" :rows="2" />
          </div>
        </div>
        <div class="drawer-footer">
          <el-button class="drawer-action-btn" plain @click="cancelEdit">取消</el-button>
          <el-button class="drawer-action-btn" type="primary" @click="save">保存</el-button>
        </div>
      </template>
    </el-drawer>

    <!-- AI 方案对话框（保留原有能力） -->
    <el-dialog v-model="showAdvise" title="AI 储蓄方案" width="520px">
      <el-form label-width="110px">
        <el-form-item label="月净现金流">
          <el-input-number
            v-model="advise.monthly"
            :min="0" :step="500" controls-position="right" style="width:100%"
          />
        </el-form-item>
      </el-form>
      <el-button type="primary" :loading="advise.loading" @click="fetchAdvise">
        让 AI 生成方案
      </el-button>
      <div v-if="advise.reply" class="advise-reply">
        <div v-html="renderMarkdown(advise.reply)"></div>
      </div>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useInvestmentStore } from '@/stores/investment'
import { useUserStore } from '@/stores/user'

const props = defineProps({ goals: { type: Array, default: () => [] } })

const store = useInvestmentStore()
const userStore = useUserStore()

const showDrawer = ref(false)
const drawerMode = ref('view')
const popoverRow = ref(null)
const editingRow = ref(null)

const sortedGoals = computed(() =>
  [...props.goals].sort((a, b) => (a.priority || 3) - (b.priority || 3))
)

function priorityClass(p) {
  const n = Number(p) || 3
  if (n <= 2) return 'high'
  if (n === 3) return 'mid'
  return 'low'
}

function priorityLabel(p) {
  const n = Number(p) || 3
  if (n === 1) return '最高'
  if (n === 2) return '高'
  if (n === 3) return '中'
  if (n === 4) return '低'
  return '最低'
}

function priorityHint(p) {
  const n = Number(p) || 3
  if (n <= 2) return '高优先级：AI 建议采用激进档位加速完成'
  if (n === 3) return '默认优先级：AI 建议平衡档位'
  return '低优先级：AI 建议保守档位或延长期限'
}

function openCreate() {
  editingRow.value = {
    id: null, name: '', target_amount: 0, current_progress: 0,
    deadline: '', priority: 3, note: '',
  }
  popoverRow.value = null
  drawerMode.value = 'edit'
  showDrawer.value = true
}

function openView(g) {
  popoverRow.value = g
  drawerMode.value = 'view'
  showDrawer.value = true
}

function startEdit() {
  editingRow.value = {
    id: popoverRow.value.id,
    name: popoverRow.value.name,
    target_amount: popoverRow.value.target_amount,
    current_progress: popoverRow.value.current_progress || 0,
    deadline: popoverRow.value.deadline || '',
    priority: popoverRow.value.priority || 3,
    note: popoverRow.value.note || '',
  }
  drawerMode.value = 'edit'
}

function cancelEdit() {
  if (popoverRow.value) {
    drawerMode.value = 'view'
    editingRow.value = null
  } else {
    showDrawer.value = false
  }
}

function onDrawerClose() {
  drawerMode.value = 'view'
  editingRow.value = null
}

async function save() {
  const r = editingRow.value
  if (!r.name || r.target_amount <= 0) {
    ElMessage.warning('请填写名称和目标金额')
    return
  }
  try {
    if (r.id) {
      await store.updateGoal(r.id, { ...r })
      ElMessage.success('已更新目标')
      const fresh = store.goals.find(x => x.id === r.id)
      if (fresh) popoverRow.value = fresh
      drawerMode.value = 'view'
    } else {
      await store.createGoal({ ...r })
      ElMessage.success('已创建目标')
      showDrawer.value = false
    }
    store.bumpRefresh()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || '保存失败')
  }
}

async function deleteFromDrawer() {
  try {
    await ElMessageBox.confirm(
      `确定删除目标「${popoverRow.value.name}」？`,
      '确认删除', { type: 'warning' },
    )
    await store.deleteGoal(popoverRow.value.id)
    ElMessage.success('已删除')
    showDrawer.value = false
    store.bumpRefresh()
  } catch { /* 取消 */ }
}

function pct(g) {
  if (!g?.target_amount) return 0
  return Math.min(100, Math.round((g.current_progress || 0) / g.target_amount * 100))
}

function pctColor(p) {
  if (p >= 100) return '#22C55E'
  if (p >= 60) return 'var(--color-primary)'
  if (p >= 30) return '#60A5FA'
  return '#F59E0B'
}

const advise = reactive({ loading: false, monthly: 0, reply: '', goal: null })
const showAdvise = ref(false)

function openAdvise(g) {
  advise.goal = g
  advise.monthly = 0
  advise.reply = ''
  showAdvise.value = true
}

async function fetchAdvise() {
  if (!advise.goal) return
  advise.loading = true
  try {
    const res = await store.askAdvisor({
      mode: 'goal',
      goal_id: advise.goal.id,
      monthly_net_cashflow: advise.monthly,
      llm: userStore.llmPayload,
    })
    advise.reply = res.reply || ''
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || 'AI 分析失败')
  } finally {
    advise.loading = false
  }
}

// 轻量 Markdown 渲染
function renderMarkdown(md) {
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const lines = md.split('\n')
  const out = []
  let tableRows = []
  const flushTable = () => {
    if (tableRows.length) {
      out.push('<table class="md-table">' + tableRows.map((r, i) =>
        `<tr>${r.map(c => `<${i === 0 ? 'th' : 'td'}>${c}</${i === 0 ? 'th' : 'td'}>`).join('')}</tr>`
      ).join('') + '</table>')
      tableRows = []
    }
  }
  for (const raw of lines) {
    const line = raw.trimEnd()
    if (line.startsWith('|') && line.endsWith('|')) {
      const cells = line.slice(1, -1).split('|').map(s => esc(s.trim()))
      if (cells.every(c => /^:?-+:?$/.test(c))) continue
      tableRows.push(cells); continue
    }
    flushTable()
    const s = esc(line)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
    out.push(s ? `<p>${s}</p>` : '<br/>')
  }
  flushTable()
  return out.join('')
}
</script>

<style scoped>
.header-row {
  display: flex; justify-content: space-between; align-items: center; width: 100%;
}
.empty {
  text-align: center; color: var(--color-text-muted); padding: 24px 0;
}
.goals {
  display: flex; flex-direction: column; gap: 16px;
}
.goal-item {
  padding: 12px 14px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: #F8FAFF;
  cursor: pointer;
  transition: box-shadow 0.2s;
}
.goal-item:hover { box-shadow: 0 2px 8px rgba(59, 130, 246, 0.15); }
.goal-head {
  display: flex; justify-content: space-between; margin-bottom: 6px;
  font-weight: 600; color: var(--color-text);
  align-items: center;
}
.goal-title { display: flex; gap: 8px; align-items: center; min-width: 0; }
.goal-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.goal-amount {
  color: var(--color-primary);
  font-variant-numeric: tabular-nums;
}
.goal-meta {
  display: flex; justify-content: space-between; margin-top: 6px;
  font-size: 12px; color: var(--color-text-muted);
}
.goal-meta .actions { display: flex; gap: 4px; }

/* 优先级徽章：高=红 / 中=橙 / 低=灰 */
.priority-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.4;
  letter-spacing: 0.5px;
  flex-shrink: 0;
}
.priority-badge.high { background: #FEE2E2; color: #B91C1C; }
.priority-badge.mid  { background: #FFEDD5; color: #C2410C; }
.priority-badge.low  { background: #F3F4F6; color: #6B7280; }
.priority-meaning {
  display: block; margin-top: 4px;
  font-size: 11px; color: var(--color-text-muted); font-weight: 400;
  max-width: 220px; white-space: normal; text-align: right;
}
.option-hint { margin-left: 8px; font-size: 12px; color: var(--color-text-muted); }

/* 抽屉样式（和资产表共享风格） */
:deep(.goal-drawer) {
  border-radius: 16px 16px 0 0 !important;
  box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.12) !important;
}
:deep(.goal-drawer .el-drawer__body) {
  padding: 0; display: flex; flex-direction: column;
}
.drawer-handle-bar {
  width: 36px; height: 4px; background: #d1d5db;
  border-radius: 2px; margin: 10px auto 0; flex-shrink: 0;
}
.drawer-body {
  padding: 8px 24px 12px; display: flex; flex-direction: column; flex: 1;
  overflow-y: auto;
}
.drawer-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 13px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.drawer-row:last-child { border-bottom: none; }
.drawer-label { font-size: 13px; color: var(--color-text-muted); font-weight: 500; }
.drawer-value { font-size: 15px; font-weight: 600; max-width: 65%; text-align: right; word-break: break-all; }
.drawer-value.text-normal { font-weight: 400; color: var(--color-text); }
.drawer-edit-title { font-size: 15px; font-weight: 600; padding: 14px 24px 6px; flex-shrink: 0; }
.drawer-edit-form {
  padding: 4px 24px 0; display: flex; flex-direction: column; gap: 14px;
  flex: 1; overflow-y: auto;
}
.drawer-edit-field { display: flex; flex-direction: column; gap: 5px; }
.drawer-edit-label { font-size: 12px; color: var(--color-text-muted); font-weight: 500; }
.drawer-footer {
  display: flex; gap: 10px; padding: 14px 24px 28px;
  border-top: 1px solid var(--el-border-color-lighter); flex-shrink: 0;
}
.drawer-action-btn { flex: 1; }

.advise-reply {
  margin-top: 16px;
  padding: 12px 14px;
  background: var(--color-primary-light);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  max-height: 380px;
  overflow-y: auto;
  font-size: 13px;
  line-height: 1.7;
}
.advise-reply :deep(.md-table) { border-collapse: collapse; width: 100%; margin: 8px 0; }
.advise-reply :deep(.md-table th),
.advise-reply :deep(.md-table td) {
  border: 1px solid var(--color-border); padding: 6px 10px; text-align: left;
}
.advise-reply :deep(.md-table th) {
  background: var(--color-primary-light); color: var(--color-primary);
}
</style>
