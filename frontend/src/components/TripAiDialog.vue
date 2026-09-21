<!-- components/TripAiDialog.vue — AI 生成行程:粘贴行程单 / 说一句话

     生成是多步的(骨架 + 每天一次调用),所以这里不是"点一下等一个结果",
     而是提交后转成进度面板:每一步单独显示状态,失败的天可以单独重试。
     生成完的内容全都落在普通的行程里,和手填的一样可以改。 -->
<template>
  <el-dialog
    :model-value="open"
    :title="job ? 'AI 正在生成行程' : '✨ AI 生成行程'"
    :width="dialogWidth"
    :close-on-click-modal="false"
    @update:model-value="close"
  >
    <!-- 输入 -->
    <template v-if="!job">
      <div class="ai-tabs">
        <button
          v-for="t in TABS"
          :key="t.key"
          type="button"
          class="ai-tab"
          :class="{ on: tab === t.key }"
          @click="tab = t.key"
        >{{ t.label }}</button>
      </div>

      <template v-if="tab === 'notice'">
        <p class="ai-hint">
          把旅行社发的行程单整段粘进来。AI 会先理出每天的主线,再逐天展开成
          时间轴、景点、贴士和住宿——<b>之后每一项你都能自己改</b>。
        </p>
        <el-input
          v-model="notice"
          type="textarea"
          :rows="9"
          placeholder="粘贴行程单原文…"
        />
        <div class="ai-count" :class="{ over: notice.length > 20000 }">
          {{ notice.length }} / 20000
        </div>
      </template>

      <template v-else>
        <p class="ai-hint">
          说一句就行,比如「十月初想去冰岛看极光,大概八天」。日期留空的话
          AI 会按常见玩法建议一个。
        </p>
        <el-input v-model="idea" type="textarea" :rows="3" placeholder="我想去…" />
        <el-form label-width="64px" size="small" class="ai-form">
          <el-form-item label="日期">
            <el-date-picker
              v-model="range"
              type="daterange"
              value-format="YYYY-MM-DD"
              start-placeholder="出发"
              end-placeholder="返程"
              style="width:100%"
            />
          </el-form-item>
          <el-form-item label="天数">
            <el-input-number v-model="days" :min="1" :max="30" size="small" />
            <span class="ai-dim">没给日期时按天数排</span>
          </el-form-item>
        </el-form>
      </template>

      <el-form label-width="64px" size="small">
        <el-form-item label="主题色">
          <div class="accent-picker">
            <button
              v-for="a in accents"
              :key="a.key"
              type="button"
              class="accent-dot"
              :class="{ on: accent === a.key }"
              :style="{ background: a.color }"
              :title="a.label"
              @click="accent = a.key"
            />
          </div>
        </el-form-item>
      </el-form>

      <p v-if="err" class="ai-err">{{ err }}</p>
    </template>

    <!-- 进度 -->
    <template v-else>
      <div class="ai-prog">
        <div class="ai-prog-bar">
          <div class="ai-prog-fill" :style="{ width: pct + '%' }"></div>
        </div>
        <div class="ai-prog-t">
          <span>{{ statusText }}</span>
          <b>{{ job.done }} / {{ job.total || '…' }}</b>
        </div>
      </div>

      <ul class="ai-steps">
        <li v-for="s in job.steps" :key="s.key" :class="s.status">
          <span class="ai-step-i">{{ ICON[s.status] || '·' }}</span>
          <span class="ai-step-l">{{ s.label }}</span>
          <span v-if="s.error" class="ai-step-e">{{ s.error }}</span>
        </li>
      </ul>

      <p v-if="job.error" class="ai-err">{{ job.error }}</p>
      <p v-else-if="job.status === 'done'" class="ai-done">
        生成完了。内容都在行程里,哪儿不对直接改——AI 写的只是初稿。
      </p>
    </template>

    <template #footer>
      <template v-if="!job">
        <el-button @click="close">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">开始生成</el-button>
      </template>
      <template v-else>
        <el-button
          v-if="job.status === 'running' || job.status === 'pending'"
          @click="cancel"
        >停下</el-button>
        <el-button
          v-if="canRetry"
          @click="retry"
        >重试没成功的</el-button>
        <el-button type="primary" @click="close">
          {{ job.status === 'done' ? '去看看' : '关闭' }}
        </el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, onBeforeUnmount, watch } from 'vue'
import api from '@/api'

const props = defineProps({
  open: { type: Boolean, default: false },
  accents: { type: Array, default: () => [] },
  // 给已有行程补全空白天时传进来;不传就是新建一趟
  tripId: { type: Number, default: 0 },
})
const emit = defineEmits(['close', 'created'])

const TABS = [
  { key: 'notice', label: '粘贴行程单' },
  { key: 'idea', label: '说一句话' },
]
const ICON = { pending: '·', running: '⏳', done: '✓', failed: '✕', skipped: '—' }

const tab = ref('notice')
const notice = ref('')
const idea = ref('')
const range = ref([])
const days = ref(7)
const accent = ref('glacier')
const submitting = ref(false)
const err = ref('')
const job = ref(null)
let timer = null

const dialogWidth = computed(() => window.innerWidth < 768 ? 'calc(100vw - 24px)' : '560px')
const pct = computed(() => {
  const j = job.value
  if (!j || !j.total) return 6
  return Math.round(j.done / j.total * 100)
})
const statusText = computed(() => ({
  pending: '排队中…', running: '生成中…', done: '完成',
  failed: '中断了', cancelled: '已停下',
}[job.value?.status] || ''))
const canRetry = computed(() =>
  job.value && ['failed', 'cancelled'].includes(job.value.status) ||
  (job.value?.status === 'done' && job.value.steps.some(s => s.status === 'failed')))

watch(() => props.open, (v) => { if (!v) stopPoll() })

function stopPoll() {
  if (timer) { clearTimeout(timer); timer = null }
}

async function poll(id) {
  try {
    const res = await api.get(`/api/trips/ai/jobs/${id}`)
    job.value = res.data
    if (['pending', 'running'].includes(res.data.status)) {
      timer = setTimeout(() => poll(id), 1500)
    }
  } catch {
    timer = setTimeout(() => poll(id), 3000)
  }
}

async function submit() {
  err.value = ''
  const body = { accent: accent.value }
  if (tab.value === 'notice') {
    if (!notice.value.trim()) { err.value = '先把行程单粘进来'; return }
    body.notice = notice.value
  } else {
    if (!idea.value.trim()) { err.value = '说一句你想去哪'; return }
    body.idea = idea.value
    if (range.value?.length === 2) {
      body.start_date = range.value[0]
      body.end_date = range.value[1]
    } else {
      body.days = days.value
    }
  }
  submitting.value = true
  try {
    const url = props.tripId
      ? `/api/trips/${props.tripId}/ai/fill`
      : '/api/trips/ai/generate'
    const res = await api.post(url, body)
    job.value = { status: 'pending', steps: [], done: 0, total: 0, id: res.data.job_id }
    poll(res.data.job_id)
  } catch (e) {
    err.value = e?.response?.data?.error || '提交失败'
  } finally {
    submitting.value = false
  }
}

async function cancel() {
  if (!job.value?.id) return
  try { await api.post(`/api/trips/ai/jobs/${job.value.id}/cancel`) } catch { /* 忽略 */ }
}

async function retry() {
  if (!job.value?.id) return
  try {
    await api.post(`/api/trips/ai/jobs/${job.value.id}/retry`)
    poll(job.value.id)
  } catch (e) {
    err.value = e?.response?.data?.error || '重试失败'
  }
}

function close() {
  stopPoll()
  const tid = job.value?.trip_id
  const finished = job.value && job.value.status !== 'pending' && job.value.status !== 'running'
  job.value = null
  notice.value = ''
  idea.value = ''
  emit('close')
  if (tid && finished) emit('created', tid)
}

onBeforeUnmount(stopPoll)
</script>

<style scoped>
.ai-tabs { display: flex; gap: 6px; margin-bottom: 10px; }
.ai-tab {
  appearance: none; border: 1px solid var(--color-border-light); background: var(--color-surface);
  color: var(--color-text-muted); font: inherit; font-size: 13px; font-weight: 700;
  padding: 5px 14px; border-radius: 999px; cursor: pointer;
}
.ai-tab.on { background: var(--color-primary); border-color: var(--color-primary); color: #fff; }

.ai-hint { font-size: 12.5px; line-height: 1.7; color: var(--color-text-muted); margin: 0 0 8px; }
.ai-count { text-align: right; font-size: 11px; color: var(--color-text-muted); margin-top: 4px; }
.ai-count.over { color: var(--color-error, #e05a5a); }
.ai-form { margin-top: 10px; }
.ai-dim { font-size: 11px; color: var(--color-text-muted); margin-left: 8px; }
.ai-err { margin: 10px 0 0; font-size: 12.5px; color: var(--color-error, #e05a5a); }
.ai-done { margin: 10px 0 0; font-size: 12.5px; color: var(--color-text-muted); }

.ai-prog-bar { height: 6px; border-radius: 999px; background: var(--color-border-light); overflow: hidden; }
.ai-prog-fill { height: 100%; background: var(--color-primary); transition: width .3s ease; }
.ai-prog-t {
  display: flex; justify-content: space-between; align-items: baseline;
  margin-top: 6px; font-size: 12px; color: var(--color-text-muted);
}
.ai-prog-t b { font-variant-numeric: tabular-nums; }

.ai-steps { list-style: none; margin: 12px 0 0; padding: 0; max-height: 44vh; overflow-y: auto; }
.ai-steps li {
  display: flex; align-items: baseline; gap: 8px; padding: 4px 0;
  font-size: 13px; color: var(--color-text);
}
.ai-steps li.pending { color: var(--color-text-muted); opacity: .7; }
.ai-steps li.failed { color: var(--color-error, #e05a5a); }
.ai-step-i { width: 16px; flex-shrink: 0; text-align: center; }
.ai-step-l { flex: 1; min-width: 0; }
.ai-step-e { font-size: 11px; color: var(--color-error, #e05a5a); }

.accent-picker { display: flex; gap: 8px; }
.accent-dot {
  width: 24px; height: 24px; border-radius: 50%;
  border: 2px solid transparent; cursor: pointer; padding: 0;
  box-shadow: 0 2px 0 0 rgba(0,0,0,.15);
}
.accent-dot.on { border-color: var(--color-text-strong); transform: scale(1.12); }
</style>
