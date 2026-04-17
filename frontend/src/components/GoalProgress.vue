<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <span>🎯 理财目标</span>
        <el-button size="small" type="primary" @click="showCreate = true">新增目标</el-button>
      </div>
    </template>

    <div v-if="!goals.length" class="empty">还没有设置目标。设定一个短/中期目标，让攒钱更有动力～</div>

    <div v-else class="goals">
      <div v-for="g in goals" :key="g.id" class="goal-item">
        <div class="goal-head">
          <span class="goal-name">{{ g.name }}</span>
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
          <span class="actions">
            <el-button size="small" text @click="openAdvise(g)">AI 方案</el-button>
            <el-button size="small" text @click="edit(g)">编辑</el-button>
            <el-button size="small" text type="danger" @click="remove(g)">删除</el-button>
          </span>
        </div>
      </div>
    </div>

    <!-- 新增/编辑 -->
    <el-dialog v-model="showCreate" :title="editing ? '编辑目标' : '新增目标'" width="420px">
      <el-form label-width="90px">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="如：买房首付" />
        </el-form-item>
        <el-form-item label="目标金额">
          <el-input-number v-model="form.target_amount" :min="0" :step="1000" controls-position="right" style="width:100%" />
        </el-form-item>
        <el-form-item label="已完成">
          <el-input-number v-model="form.current_progress" :min="0" :step="100" controls-position="right" style="width:100%" />
        </el-form-item>
        <el-form-item label="截止日期">
          <el-date-picker v-model="form.deadline" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="form.priority" style="width:100%">
            <el-option :value="1" label="1 · 最高" />
            <el-option :value="2" label="2" />
            <el-option :value="3" label="3 · 默认" />
            <el-option :value="4" label="4" />
            <el-option :value="5" label="5 · 最低" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- AI 方案 -->
    <el-dialog v-model="showAdvise" title="AI 储蓄方案" width="520px">
      <el-form label-width="110px">
        <el-form-item label="月净现金流">
          <el-input-number v-model="advise.monthly" :min="0" :step="500" controls-position="right" style="width:100%" />
        </el-form-item>
      </el-form>
      <el-button type="primary" :loading="advise.loading" @click="fetchAdvise">让 AI 生成方案</el-button>
      <div v-if="advise.reply" class="advise-reply">
        <div v-html="renderMarkdown(advise.reply)"></div>
      </div>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useInvestmentStore } from '@/stores/investment'
import { useUserStore } from '@/stores/user'

const props = defineProps({ goals: { type: Array, default: () => [] } })

const store = useInvestmentStore()
const userStore = useUserStore()

const showCreate = ref(false)
const editing = ref(null)
const form = reactive({
  name: '', target_amount: 0, current_progress: 0, deadline: '', priority: 3,
})

function resetForm() {
  form.name = ''; form.target_amount = 0; form.current_progress = 0
  form.deadline = ''; form.priority = 3
  editing.value = null
}

function edit(g) {
  editing.value = g
  form.name = g.name
  form.target_amount = g.target_amount
  form.current_progress = g.current_progress || 0
  form.deadline = g.deadline || ''
  form.priority = g.priority || 3
  showCreate.value = true
}

async function save() {
  if (!form.name || form.target_amount <= 0) {
    ElMessage.warning('请填写名称和目标金额')
    return
  }
  try {
    if (editing.value) {
      await store.updateGoal(editing.value.id, { ...form })
      ElMessage.success('已更新目标')
    } else {
      await store.createGoal({ ...form })
      ElMessage.success('已创建目标')
    }
    showCreate.value = false
    resetForm()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '保存失败')
  }
}

async function remove(g) {
  try {
    await ElMessageBox.confirm(`确定删除目标「${g.name}」？`, '确认删除', { type: 'warning' })
    await store.deleteGoal(g.id)
    ElMessage.success('已删除')
  } catch { /* 取消 */ }
}

function pct(g) {
  if (!g.target_amount) return 0
  return Math.min(100, Math.round((g.current_progress || 0) / g.target_amount * 100))
}

function pctColor(p) {
  if (p >= 100) return '#22C55E'
  if (p >= 60) return '#2563EB'
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
    ElMessage.error(e.response?.data?.message || 'AI 分析失败')
  } finally {
    advise.loading = false
  }
}

// 非常轻量的 Markdown 渲染（支持 **bold**、行内代码、换行、表格）
function renderMarkdown(md) {
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const lines = md.split('\n')
  const out = []
  let inTable = false
  let tableRows = []
  const flushTable = () => {
    if (tableRows.length) {
      out.push('<table class="md-table">' + tableRows.map((r, i) =>
        `<tr>${r.map(c => `<${i === 0 ? 'th' : 'td'}>${c}</${i === 0 ? 'th' : 'td'}>`).join('')}</tr>`
      ).join('') + '</table>')
      tableRows = []
    }
    inTable = false
  }
  for (const raw of lines) {
    const line = raw.trimEnd()
    if (line.startsWith('|') && line.endsWith('|')) {
      const cells = line.slice(1, -1).split('|').map(s => esc(s.trim()))
      if (cells.every(c => /^-+:?$/.test(c) || /^:?-+:?$/.test(c))) continue
      tableRows.push(cells); inTable = true; continue
    }
    if (inTable) flushTable()
    let s = esc(line)
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
}
.goal-head {
  display: flex; justify-content: space-between; margin-bottom: 6px;
  font-weight: 600; color: var(--color-text);
}
.goal-amount {
  color: var(--color-primary);
  font-variant-numeric: tabular-nums;
}
.goal-meta {
  display: flex; justify-content: space-between; margin-top: 6px;
  font-size: 12px; color: var(--color-text-muted);
}
.goal-meta .actions { display: flex; gap: 4px; }
.advise-reply {
  margin-top: 16px;
  padding: 12px 14px;
  background: #F0F7FF;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  max-height: 380px;
  overflow-y: auto;
  font-size: 13px;
  line-height: 1.7;
}
.advise-reply :deep(.md-table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
}
.advise-reply :deep(.md-table th),
.advise-reply :deep(.md-table td) {
  border: 1px solid var(--color-border);
  padding: 6px 10px;
  text-align: left;
}
.advise-reply :deep(.md-table th) {
  background: var(--color-primary-light);
  color: var(--color-primary);
}
</style>
