<!-- components/TripJournalExpenses.vue — 从手记里找花费,逐条确认后记进账本

     这是「旅行计划」和「记账」之间那条线的另一半:trip_id 让账能算到某趟头上,
     这里让写在手记里的花费变成账。

     AI 只负责**找出候选**。从一段游记里抽出来的金额,币种、是不是人均、
     是不是真付过,全都可能判错——所以一条都不会自动入账,全靠逐条勾选。
-->
<template>
  <div class="je">
    <div class="je-act">
      <button type="button" class="je-b" :disabled="ai.running || !hasText" @click="scan">
        <span v-if="ai.running" class="je-spin" aria-hidden="true"></span>
        {{ ai.running ? `找花费中… ${aiSecs}s` : '📒 从手记里找花费' }}
      </button>
      <span v-if="!hasText" class="je-dim">先写点手记</span>
      <span v-else-if="ai.running" class="je-dim">要十几秒,切走也不会断</span>
      <span v-if="err" class="je-err">{{ err }}</span>
    </div>

    <div v-if="rows.length" class="je-box">
      <div class="je-head">
        <span>找到 {{ rows.length }} 笔,勾选要记的</span>
        <button type="button" class="je-b tiny" @click="toggleAll">
          {{ allPicked ? '全不选' : '全选' }}
        </button>
        <button type="button" class="je-b tiny" @click="discard">丢弃</button>
      </div>

      <div v-for="(r, i) in rows" :key="i" class="je-row" :class="{ on: r.pick }">
        <label class="je-line1">
          <input type="checkbox" v-model="r.pick">
          <input v-model="r.note" class="je-in je-note" placeholder="备注">
          <select v-model="r.kind" class="je-in je-kind">
            <option value="expense">支出</option>
            <option value="income">退款</option>
          </select>
        </label>

        <div class="je-line2">
          <input v-model="r.category" class="je-in je-cat" placeholder="分类">
          <input v-model="r.date" class="je-in je-date" placeholder="YYYY-MM-DD">
          <span class="je-gap"></span>
          <span class="je-amt">¥{{ cny(r) }}</span>
        </div>

        <!-- 账本没有币种这一列,所以外币必须在这儿折算完再入账。
             汇率是今天的,不是那天的——差很多的话自己改。 -->
        <div v-if="r.currency && r.currency !== 'CNY'" class="je-line3">
          <span class="je-dim">原币</span>
          <input v-model.number="r.amount" class="je-in je-num" type="number" step="0.01">
          <input v-model="r.currency" class="je-in je-cur" maxlength="3">
          <span class="je-dim">× 汇率</span>
          <input v-model.number="r.fx" class="je-in je-num" type="number" step="0.0001">
          <span v-if="!r.fx" class="je-err">取不到汇率,请填</span>
        </div>
        <div v-else class="je-line3">
          <span class="je-dim">金额</span>
          <input v-model.number="r.amount" class="je-in je-num" type="number" step="0.01">
          <button type="button" class="je-b tiny" @click="r.currency = 'SEK'">改成外币</button>
        </div>

        <div v-if="r.dup || !r.sure" class="je-flags">
          <span v-if="r.dup" class="je-warn">这一天已经有一笔一样金额的账了,别记重</span>
          <span v-if="!r.sure" class="je-warn">AI 不确定这笔是不是真花了</span>
        </div>
      </div>

      <div class="je-foot">
        <span class="je-dim">合计 ¥{{ pickedTotal }}</span>
        <span class="je-gap"></span>
        <button
          type="button"
          class="je-b primary"
          :disabled="!pickedCount || saving"
          @click="commit"
        >{{ saving ? '记账中…' : `记入账本(${pickedCount} 笔)` }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'
import { aiState, aiElapsed, runAiBlock, clearAiBlock } from '@/utils/aiJobs'

const props = defineProps({
  tripId: { type: Number, required: true },
  day: { type: Object, required: true },
})

const rows = ref([])
const saving = ref(false)
const localErr = ref('')

const hasText = computed(() => !!(props.day?.journal || '').trim())
// 按 key 现取:换天时组件是复用的,记死了会盯着上一天的任务
const aiKey = computed(() => `journal_expenses:${props.tripId}:${props.day?.day_no || 0}`)
const ai = computed(() => aiState(aiKey.value))
const aiSecs = computed(() => aiElapsed(aiKey.value))
const err = computed(() => ai.value.error || localErr.value)

/** 折算成人民币的金额,也就是真正会写进账本的那个数。 */
function cny(r) {
  const n = Number(r.amount) || 0
  const k = (r.currency && r.currency !== 'CNY') ? (Number(r.fx) || 0) : 1
  return Math.round(n * k * 100) / 100
}

const pickedRows = computed(() => rows.value.filter(r => r.pick))
const pickedCount = computed(() => pickedRows.value.length)
const allPicked = computed(() => rows.value.length > 0 && pickedCount.value === rows.value.length)
const pickedTotal = computed(() => Math.round(pickedRows.value.reduce(
  (s, r) => s + cny(r) * (r.kind === 'income' ? -1 : 1), 0) * 100) / 100)

/** 结果回来了就摆成可编辑的候选。默认**不勾**有疑点的那些。 */
function absorb() {
  const data = ai.value.result
  if (!data) return
  clearAiBlock(aiKey.value)
  const items = data.items || []
  if (!items.length) {
    localErr.value = '这段手记里没找到花费。写清楚金额和买了什么会更好认。'
    return
  }
  localErr.value = ''
  rows.value = items.map(x => ({
    ...x,
    fx: x.fx ?? 1,
    // 重复的和 AI 自己都不确定的默认不勾:让人主动去点,而不是默认记进去
    pick: !x.dup && !!x.sure,
  }))
}
watch(() => ai.value.result, absorb)
// 换天就把上一天的候选收起来,免得记到别天去
watch(() => props.day?.day_no, () => { rows.value = []; localErr.value = '' })

async function scan() {
  localErr.value = ''
  rows.value = []
  await runAiBlock(aiKey.value, `/api/trips/${props.tripId}/ai/block`, {
    kind: 'journal_expenses',
    day_no: props.day.day_no,
    label: `找第 ${props.day.day_no} 天的花费`,
  })
}

function toggleAll() {
  const v = !allPicked.value
  rows.value.forEach(r => { r.pick = v })
}

function discard() {
  rows.value = []
  localErr.value = ''
}

async function commit() {
  const items = pickedRows.value.map(r => ({
    note: r.note, category: r.category, date: r.date, kind: r.kind,
    amount: cny(r),            // 折算后的金额:账本里存的就是这个
  }))
  const bad = items.find(x => !(x.amount > 0))
  if (bad) {
    localErr.value = `「${bad.note || '有一笔'}」的金额算出来是 0,检查一下汇率`
    return
  }
  saving.value = true
  try {
    const { data } = await api.post(`/api/trips/${props.tripId}/journal/records`, { items })
    if (data.created) ElMessage.success(`记了 ${data.created} 笔,已归到这趟行程`)
    if (data.errors?.length) {
      localErr.value = `${data.errors.length} 笔没记成:${data.errors[0].error}`
      // 记成了的从列表里去掉,剩下的留着让人改
      const failed = new Set(data.errors.map(e => e.i))
      const picked = pickedRows.value
      rows.value = rows.value.filter(r => !r.pick || failed.has(picked.indexOf(r)))
    } else {
      rows.value = []
    }
  } catch (e) {
    localErr.value = e?.response?.data?.error || '记账失败,再试一次'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.je { margin-top: 10px; }
.je-act { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.je-b {
  appearance: none; border: 1px solid var(--trip-accent, var(--color-primary));
  background: var(--color-surface); color: var(--trip-accent, var(--color-primary));
  font: inherit; font-size: 12px; padding: 3px 12px; border-radius: 999px; cursor: pointer;
}
.je-b.tiny { font-size: 11px; padding: 2px 9px; border-color: var(--color-border-light);
  color: var(--color-text-muted); }
.je-b.primary { background: var(--trip-accent, var(--color-primary)); color: #fff; font-weight: 700; }
.je-b:disabled { opacity: .55; cursor: default; }
.je-dim { font-size: 11.5px; color: var(--color-text-muted); }
.je-err { font-size: 11.5px; color: var(--color-error, #e05a5a); }
.je-warn { font-size: 11.5px; color: var(--color-warning, #c9843a); }
.je-spin {
  display: inline-block; width: 9px; height: 9px; margin-right: 4px; vertical-align: -1px;
  border-radius: 50%; border: 2px solid currentColor; border-top-color: transparent;
  animation: je-rot .7s linear infinite;
}
@keyframes je-rot { to { transform: rotate(360deg); } }

.je-box {
  margin-top: 10px; padding: 10px; border-radius: 12px;
  border: 1px dashed var(--trip-accent, var(--color-primary));
}
.je-head {
  display: flex; align-items: center; gap: 8px; margin-bottom: 8px;
  font-size: 12px; color: var(--color-text-muted);
}
.je-head span { margin-right: auto; }

.je-row {
  border-top: 1px solid var(--color-border-light); padding: 8px 0;
  display: flex; flex-direction: column; gap: 5px; opacity: .55;
}
.je-row.on { opacity: 1; }
.je-line1 { display: flex; align-items: center; gap: 6px; cursor: pointer; }
.je-line2, .je-line3 { display: flex; align-items: center; gap: 6px; }
.je-gap { flex: 1; }
.je-in {
  font: inherit; font-size: 12.5px; padding: 4px 7px; border-radius: 8px;
  border: 1px solid var(--color-border-light);
  background: var(--color-surface); color: var(--color-text); min-width: 0;
}
.je-in:focus { outline: none; border-color: var(--trip-accent, var(--color-primary)); }
.je-note { flex: 1; }
.je-kind { flex: 0 0 5.6em; }
.je-cat { flex: 0 0 6em; }
.je-date { flex: 0 0 8.2em; font-variant-numeric: tabular-nums; }
.je-num { flex: 0 0 6em; font-variant-numeric: tabular-nums; }
.je-cur { flex: 0 0 3.6em; text-transform: uppercase; }
.je-amt { font-weight: 800; font-variant-numeric: tabular-nums; font-size: 13px; }
.je-flags { display: flex; flex-direction: column; gap: 2px; }
.je-foot {
  display: flex; align-items: center; gap: 8px;
  border-top: 1px solid var(--color-border-light); padding-top: 9px; margin-top: 3px;
}
</style>
