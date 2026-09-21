<!-- components/TripAiDialog.vue — AI 生成行程:粘贴行程单 / 说一句话

     生成是多步的(骨架 + 每天一次调用),所以这里不是"点一下等一个结果",
     而是提交后转成进度面板:每一步单独显示状态,失败的天可以单独重试。
     生成完的内容全都落在普通的行程里,和手填的一样可以改。 -->
<template>
  <el-dialog
    :model-value="open"
    :title="dialogTitle"
    :width="dialogWidth"
    :close-on-click-modal="false"
    @update:model-value="close"
  >
    <!-- 批量补景点介绍:没什么可填的,说清楚就开跑 -->
    <template v-if="!job && mode === 'spots'">
      <p class="ai-hint">
        给这趟行程里<b>还没有介绍的 {{ bareSpots || '' }} 个地点</b>各写一条。
        <b>已经写过的不会动</b>——包括你自己写的。
      </p>
      <p class="ai-hint">
        按天分批生成,一天一次调用;中途可以停,某天失败了也只影响那一天。
        写完之后每条都还能自己改。
      </p>
      <p v-if="err" class="ai-err">{{ err }}</p>
    </template>

    <!-- 补全已有行程:只补空白的天,不问标题日期主题色 -->
    <template v-else-if="!job && isFill">
      <p class="ai-hint">
        把这趟行程里<b>还没有内容的 {{ blankDays || '' }} 天</b>补上。
        已经填过的天不会动——包括你自己改过的。
      </p>
      <p class="ai-hint">
        有行程单原文的话一起给,补出来更贴近实际;没有就让 AI 按每天的主线发挥。
      </p>

      <div
        class="ai-drop"
        :class="{ busy: reading }"
        role="button"
        tabindex="0"
        @click="fileRef?.click()"
        @keydown.enter="fileRef?.click()"
        @dragover.prevent
        @drop.prevent="onDrop"
      >
        <span v-if="reading">正在读取 {{ pickedName }}…</span>
        <span v-else-if="pickedName" class="ai-drop-ok">
          ✓ 已读入 <b>{{ pickedName }}</b> · {{ notice.length }} 字
        </span>
        <template v-else>
          <b>选择行程单</b>（可选）· Word / PDF / HTML / txt
        </template>
      </div>
      <p v-if="readErr" class="ai-err">{{ readErr }}</p>
      <el-input
        v-model="notice"
        type="textarea"
        :rows="5"
        placeholder="也可以把行程单粘在这里（可选）"
      />
      <p v-if="err" class="ai-err">{{ err }}</p>
    </template>

    <!-- 新建 -->
    <template v-else-if="!job && mode === 'new'">
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
        <!-- 点整块区域或者把文件拖进来都行 -->
        <div
          class="ai-drop"
          :class="{ busy: reading }"
          role="button"
          tabindex="0"
          @click="fileRef?.click()"
          @keydown.enter="fileRef?.click()"
          @dragover.prevent
          @drop.prevent="onDrop"
        >
          <span v-if="reading">正在读取 {{ pickedName }}…</span>
          <span v-else-if="pickedName" class="ai-drop-ok">
            ✓ 已读入 <b>{{ pickedName }}</b> · {{ notice.length }} 字,下面可以改
          </span>
          <template v-else>
            <b>选择文件</b> 或拖进来 · 支持 Word(.docx)、PDF、HTML、txt
          </template>
        </div>
        <input
          ref="fileRef"
          type="file"
          accept=".docx,.pdf,.html,.htm,.txt,.md"
          hidden
          :disabled="reading"
          @change="onPick"
        >
        <p v-if="readErr" class="ai-err">{{ readErr }}</p>

        <el-input
          v-model="notice"
          type="textarea"
          :rows="9"
          placeholder="也可以直接把行程单粘在这里…"
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

      <!-- 不用 el-form-item:那个左侧标签列会把颜色挤到换行,窄屏尤其难看 -->
      <div class="accent-block">
        <div class="accent-label">
          主题色<span>自动 = 让 AI 按行程气质挑</span>
        </div>
        <div class="accent-picker">
          <button
            type="button"
            class="accent-auto"
            :class="{ on: !accent }"
            @click="accent = ''"
          >自动</button>
          <button
            v-for="a in accents"
            :key="a.key"
            type="button"
            class="accent-dot"
            :class="{ on: accent === a.key }"
            :style="{ background: a.color }"
            :title="a.label"
            @click="accent = a.key"
          >
            <span v-if="accent === a.key" aria-hidden="true">✓</span>
          </button>
        </div>
      </div>

      <p v-if="err" class="ai-err">{{ err }}</p>
    </template>

    <!-- 进度 -->
    <template v-else>
      <p class="ai-hint ai-bg">
        生成在后台跑,关掉这个框、去别的页面都不会停。回到旅行计划就能接着看。
      </p>
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
        <template v-if="!job.steps.length">
          没有需要补的了。
        </template>
        <template v-else>
          写完了。内容都在行程里,哪儿不对直接改——AI 写的只是初稿。
        </template>
      </p>
    </template>

    <template #footer>
      <template v-if="!job">
        <el-button @click="close">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">
          {{ submitLabel }}
        </el-button>
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
  // 接上一个已经在跑的任务(从别的页面回来时)
  jobId: { type: Number, default: 0 },
  // 补全模式下用来告诉用户会补几天
  blankDays: { type: Number, default: 0 },
  // 'new' 新建 | 'fill' 补空白天 | 'spots' 批量补景点介绍
  mode: { type: String, default: 'new' },
  bareSpots: { type: Number, default: 0 },
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
const accent = ref('')          // 空 = 交给 AI 挑
const reading = ref(false)
const pickedName = ref('')
const readErr = ref('')
const fileRef = ref(null)
const submitting = ref(false)
const err = ref('')
const job = ref(null)
let timer = null

const isFill = computed(() => props.mode === 'fill')
const dialogTitle = computed(() => {
  const running = !!job.value
  if (props.mode === 'spots') return running ? 'AI 正在写介绍' : '✨ 给景点补介绍'
  if (isFill.value) return running ? 'AI 正在补全' : '✨ 补全空白的天'
  return running ? 'AI 正在生成行程' : '✨ AI 生成行程'
})
const submitLabel = computed(() => ({
  spots: '开始写', fill: '开始补全',
}[props.mode] || '开始生成'))
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

watch(() => props.open, (v) => {
  if (!v) { stopPoll(); return }
  // 带着 jobId 打开 = 从别的地方回来接进度,不用再填一遍表单
  if (props.jobId) {
    job.value = { status: 'running', steps: [], done: 0, total: 0, id: props.jobId }
    poll(props.jobId)
  }
}, { immediate: true })

function stopPoll() {
  if (timer) { clearTimeout(timer); timer = null }
}

async function poll(id) {
  try {
    const res = await api.get(`/api/ai-jobs/${id}`)
    job.value = res.data
    if (['pending', 'running'].includes(res.data.status)) {
      timer = setTimeout(() => poll(id), 1500)
    }
  } catch {
    timer = setTimeout(() => poll(id), 3000)
  }
}

/** 只抽文本,不直接生成:行程单里常有排版垃圾,让用户过目一眼再生成更稳。 */
async function readFile(file) {
  if (!file) return
  reading.value = true
  readErr.value = ''
  pickedName.value = file.name
  try {
    const fd = new FormData()
    fd.append('file', file)
    const res = await api.post('/api/trips/ai/extract', fd)
    notice.value = res.data.text || ''
  } catch (e) {
    readErr.value = e?.response?.data?.error || '读取失败'
    pickedName.value = ''
  } finally {
    reading.value = false
  }
}
function onPick(e) {
  const f = e.target.files?.[0]
  e.target.value = ''
  readFile(f)
}
function onDrop(e) { readFile(e.dataTransfer?.files?.[0]) }

async function submit() {
  err.value = ''
  const body = {}
  if (props.mode === 'spots') {
    submitting.value = true
    try {
      const res = await api.post(`/api/trips/${props.tripId}/ai/spots`, {})
      job.value = { status: 'pending', steps: [], done: 0, total: 0, id: res.data.job_id }
      poll(res.data.job_id)
    } catch (e) {
      err.value = e?.response?.data?.error || '提交失败'
    } finally {
      submitting.value = false
    }
    return
  }
  if (isFill.value) {
    if (notice.value.trim()) body.notice = notice.value
    submitting.value = true
    try {
      const res = await api.post(`/api/trips/${props.tripId}/ai/fill`, body)
      job.value = { status: 'pending', steps: [], done: 0, total: 0, id: res.data.job_id }
      poll(res.data.job_id)
    } catch (e) {
      err.value = e?.response?.data?.error || '提交失败'
    } finally {
      submitting.value = false
    }
    return
  }
  if (accent.value) body.accent = accent.value
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
    const res = await api.post('/api/trips/ai/generate', body)
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
  try { await api.post(`/api/ai-jobs/${job.value.id}/cancel`) } catch { /* 忽略 */ }
}

async function retry() {
  if (!job.value?.id) return
  try {
    await api.post(`/api/ai-jobs/${job.value.id}/retry`)
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
  pickedName.value = ''
  readErr.value = ''
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

.ai-bg { margin-bottom: 12px; }
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

.ai-drop {
  display: block; text-align: center; cursor: pointer;
  border: 1.5px dashed var(--color-primary); border-radius: 12px;
  padding: 14px 12px; margin-bottom: 10px; font-size: 12.5px;
  color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary-light) 45%, transparent);
}
.ai-drop:hover { background: var(--color-primary-light); }
.ai-drop.busy { opacity: .6; cursor: default; }
.ai-drop-ok { color: var(--color-text); }

.accent-block { margin-top: 14px; }
.accent-label {
  display: flex; align-items: baseline; gap: 8px; margin-bottom: 7px;
  font-size: 12.5px; font-weight: 700; color: var(--color-text-strong);
}
.accent-label span { font-size: 11px; font-weight: 400; color: var(--color-text-muted); }
.accent-picker { display: flex; gap: 6px; align-items: center; }
.accent-auto {
  appearance: none; border: 1px dashed var(--color-text-muted); background: none;
  color: var(--color-text-muted); font: inherit; font-size: 12px;
  height: 26px; padding: 0 11px; border-radius: 999px; cursor: pointer; flex-shrink: 0;
}
.accent-auto.on {
  border-style: solid; border-color: var(--color-text-strong);
  color: var(--color-text-strong); font-weight: 700;
}
.accent-dot {
  width: 26px; height: 26px; border-radius: 50%; flex-shrink: 0;
  border: 0; cursor: pointer; padding: 0;
  display: grid; place-items: center;
  color: #fff; font-size: 13px; line-height: 1;
  box-shadow: inset 0 0 0 2px rgba(255, 255, 255, .55);
}
.accent-dot.on { box-shadow: 0 0 0 2px var(--color-text-strong); }
</style>
