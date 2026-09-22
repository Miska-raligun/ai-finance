<!-- components/TripPacking.vue — 打包清单:按分组勾选,进度入库(多端同步) -->
<template>
  <div class="pk">
    <div class="pk-prog">
      <span class="pk-prog-label">已备</span>
      <span class="pk-bar"><i :style="{ width: pct + '%' }" /></span>
      <span class="pk-count">{{ checkedCount }} / {{ items.length }}</span>
    </div>

    <div class="pk-ai">
      <button type="button" class="pk-ai-b" :disabled="ai.running" @click="propose">
        <span v-if="ai.running" class="pk-spin" aria-hidden="true"></span>
        {{ ai.running ? `生成中… ${aiSecs}s` : '✨ 让 AI 按这趟行程列一份' }}
      </button>
      <span v-if="ai.running" class="pk-ai-err">
        要十几秒,切到别的页面也不会断
      </span>
      <span v-if="aiErr" class="pk-ai-err">{{ aiErr }}</span>
    </div>

    <!-- AI 出的是建议:逐条挑,挑中的才入库,之后照常可改可删 -->
    <div v-if="proposed.length" class="pk-prop">
      <div class="pk-prop-h">
        <span>AI 建议 {{ picked.size }} / {{ proposed.length }}</span>
        <button type="button" class="pk-ai-b" @click="toggleAll">
          {{ picked.size === proposed.length ? '全不选' : '全选' }}
        </button>
        <button type="button" class="pk-ai-b" @click="proposed = []">丢弃</button>
        <button
          type="button"
          class="pk-ai-b primary"
          :disabled="!picked.size || adding"
          @click="acceptPicked"
        >{{ adding ? '加入中…' : `加入选中的 ${picked.size} 条` }}</button>
      </div>
      <label v-for="(it, i) in proposed" :key="i" class="pk-prop-i" :class="{ on: picked.has(i) }">
        <input type="checkbox" :checked="picked.has(i)" @change="togglePick(i)">
        <span class="pk-prop-g">{{ it.grp }}</span>
        <span class="pk-prop-l">{{ it.label }}</span>
        <span v-if="it.hint" class="pk-prop-hint">{{ it.hint }}</span>
      </label>
    </div>

    <el-empty v-if="!items.length && !proposed.length" description="还没有打包清单，在下面加第一条或让 AI 起一份" :image-size="60" />

    <section v-for="g in grouped" :key="g.name" class="pk-grp">
      <h4 class="pk-grp-t">{{ g.name || '未分组' }}</h4>
      <label v-for="it in g.items" :key="it.id" class="pk-item" :class="{ on: it.checked }">
        <input
          type="checkbox"
          :checked="!!it.checked"
          @change="toggle(it, $event.target.checked)"
        >
        <span class="pk-text">
          <span class="pk-label">{{ it.label }}</span>
          <span v-if="it.hint" class="pk-hint">{{ it.hint }}</span>
        </span>
        <button class="pk-del" title="删除" @click.prevent="remove(it)">×</button>
      </label>
    </section>

    <div class="pk-add">
      <el-input v-model="draft.grp" size="small" placeholder="分组（如 证件）" class="pk-in-grp" />
      <el-input
        v-model="draft.label"
        size="small"
        placeholder="要带的东西"
        class="pk-in-label"
        @keyup.enter="add"
      />
      <el-input v-model="draft.hint" size="small" placeholder="备注（可选）" class="pk-in-hint" />
      <el-button size="small" type="primary" :loading="saving" @click="add">添加</el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { aiState, aiElapsed, runAiBlock, clearAiBlock } from '@/utils/aiJobs'
import { ElMessage } from 'element-plus'
import api from '@/api'

const props = defineProps({
  tripId: { type: Number, required: true },
  packing: { type: Array, default: () => [] },
})
const emit = defineEmits(['changed'])

const items = computed(() => props.packing)
const saving = ref(false)
const draft = reactive({ grp: '', label: '', hint: '' })

// AI 建议:先摆出来让人挑,挑中的才入库。
// 在途状态放模块级 store,切走再回来还能接上(见 utils/aiJobs.js)
const adding = ref(false)
const proposed = ref([])
const picked = ref(new Set())
const aiKey = computed(() => `packing:${props.tripId}`)
// 按 key 现取,不在挂载时定死:换行程 / 换天时组件是复用的,
// 把 key 记死会让它一直盯着上一趟的任务,结果就落到别人身上了
const ai = computed(() => aiState(aiKey.value))
const aiSecs = computed(() => aiElapsed(aiKey.value))
const aiErr = computed(() => ai.value.error || localErr.value)
const localErr = ref('')

/** 把 store 里的结果搬到本地的待挑列表。挂载时也调一次——
 *  可能是在别的 Tab 发起的,回来正好取结果。 */
function absorb() {
  const data = ai.value.result
  if (!data) return
  const have = new Set(items.value.map(i => i.label))
  proposed.value = (data.items || []).filter(x => !have.has(x.label))
  picked.value = new Set(proposed.value.map((_, i) => i))
  localErr.value = proposed.value.length ? '' : 'AI 想到的都已经在清单里了'
  clearAiBlock(aiKey.value)
}
watch(() => ai.value.result, absorb)
onMounted(absorb)

async function propose() {
  localErr.value = ''
  await runAiBlock(aiKey.value, `/api/trips/${props.tripId}/ai/block`, { kind: 'packing' })
}

function togglePick(i) {
  const s = new Set(picked.value)
  s.has(i) ? s.delete(i) : s.add(i)
  picked.value = s
}
function toggleAll() {
  picked.value = picked.value.size === proposed.value.length
    ? new Set()
    : new Set(proposed.value.map((_, i) => i))
}

async function acceptPicked() {
  adding.value = true
  try {
    let n = items.value.length
    for (let i = 0; i < proposed.value.length; i++) {
      if (!picked.value.has(i)) continue
      const it = proposed.value[i]
      await api.post(`/api/trips/${props.tripId}/packing`, {
        grp: it.grp, label: it.label, hint: it.hint, sort_order: n++,
      })
    }
    proposed.value = []
    picked.value = new Set()
    emit('changed')
  } catch (e) {
    localErr.value = e?.response?.data?.error || '加入失败'
  } finally {
    adding.value = false
  }
}

const checkedCount = computed(() => items.value.filter(i => i.checked).length)
const pct = computed(() => items.value.length
  ? Math.round(checkedCount.value / items.value.length * 100) : 0)

/** 保持后端返回的顺序,按 grp 首次出现的次序分组。 */
const grouped = computed(() => {
  const map = new Map()
  for (const it of items.value) {
    const k = it.grp || ''
    if (!map.has(k)) map.set(k, [])
    map.get(k).push(it)
  }
  return [...map.entries()].map(([name, list]) => ({ name, items: list }))
})

async function toggle(it, checked) {
  const prev = it.checked
  it.checked = checked ? 1 : 0          // 乐观更新,失败回滚
  try {
    await api.patch(`/api/trips/${props.tripId}/packing/${it.id}`, { checked })
  } catch {
    it.checked = prev
    ElMessage.error('保存失败')
  }
}

async function add() {
  if (!draft.label.trim()) { ElMessage.warning('填一下要带的东西'); return }
  saving.value = true
  try {
    await api.post(`/api/trips/${props.tripId}/packing`, {
      grp: draft.grp, label: draft.label, hint: draft.hint,
      sort_order: items.value.length,
    })
    draft.label = ''; draft.hint = ''     // 分组留着,方便连续加同组
    emit('changed')
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || '添加失败')
  } finally {
    saving.value = false
  }
}

async function remove(it) {
  try {
    await api.delete(`/api/trips/${props.tripId}/packing/${it.id}`)
    emit('changed')
  } catch {
    ElMessage.error('删除失败')
  }
}
</script>

<style scoped>
.pk-ai { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
.pk-ai-b {
  appearance: none; border: 1px solid var(--trip-accent, var(--color-primary));
  background: var(--color-surface); color: var(--trip-accent, var(--color-primary));
  font: inherit; font-size: 12px; padding: 3px 12px; border-radius: 999px; cursor: pointer;
}
.pk-ai-b:disabled { opacity: .55; cursor: default; }
.pk-ai-b.primary {
  background: var(--trip-accent, var(--color-primary)); color: #fff; font-weight: 700;
}
.pk-ai-err { font-size: 12px; color: var(--color-text-muted); }
.pk-spin {
  display: inline-block; width: 10px; height: 10px; margin-right: 5px;
  vertical-align: -1px; border-radius: 50%;
  border: 2px solid currentColor; border-top-color: transparent;
  animation: pk-rot .7s linear infinite;
}
@keyframes pk-rot { to { transform: rotate(360deg); } }
.pk-prop {
  border: 1px dashed var(--trip-accent, var(--color-primary));
  border-radius: 12px; padding: 10px 12px; margin-bottom: 14px;
}
.pk-prop-h {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  font-size: 12px; color: var(--color-text-muted); margin-bottom: 8px;
}
.pk-prop-h span { margin-right: auto; }
.pk-prop-i {
  display: flex; align-items: baseline; gap: 8px; padding: 3px 0;
  font-size: 13px; cursor: pointer; opacity: .55;
}
.pk-prop-i.on { opacity: 1; }
.pk-prop-g { font-size: 11px; color: var(--color-text-muted); flex-shrink: 0; min-width: 4em; }
.pk-prop-l { font-weight: 600; }
.pk-prop-hint { font-size: 11.5px; color: var(--color-text-muted); }

.pk-prog { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; font-size: 12px; color: var(--color-text-muted); }
.pk-bar { flex: 1; height: 7px; border-radius: 999px; background: var(--color-surface-2, rgba(0,0,0,.07)); overflow: hidden; }
.pk-bar i { display: block; height: 100%; background: var(--trip-accent, var(--color-primary)); transition: width .25s ease; }
.pk-count { font-variant-numeric: tabular-nums; font-weight: 700; }

.pk-grp + .pk-grp { margin-top: 14px; }
.pk-grp-t { margin: 0 0 6px; font-size: 11px; font-weight: 800; letter-spacing: .08em; color: var(--trip-ink-2, var(--color-text-muted)); }

.pk-item {
  display: flex; align-items: flex-start; gap: 9px;
  padding: 6px 8px; border-radius: 9px; cursor: pointer;
  border: 1px solid transparent;
}
.pk-item:hover { background: var(--color-surface-2, rgba(0,0,0,.03)); }
.pk-item:hover .pk-del { opacity: 1; }
.pk-item input { margin-top: 3px; accent-color: var(--trip-accent, var(--color-primary)); flex-shrink: 0; }
.pk-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.pk-label { font-size: 13px; line-height: 1.45; }
.pk-item.on .pk-label { text-decoration: line-through; color: var(--color-text-muted); }
.pk-hint { font-size: 11px; color: var(--color-text-muted); }
.pk-del {
  border: 0; background: none; cursor: pointer; opacity: 0;
  color: var(--color-text-muted); font-size: 16px; line-height: 1; padding: 0 2px;
  transition: opacity .12s ease;
}
.pk-del:hover { color: var(--color-error, #e05a5a); }

.pk-add { display: flex; gap: 6px; margin-top: 16px; flex-wrap: wrap; }
.pk-in-grp { width: 110px; }
.pk-in-label { flex: 1; min-width: 130px; }
.pk-in-hint { width: 150px; }
@media (max-width: 768px) {
  .pk-in-grp, .pk-in-hint { width: 100%; }
  .pk-in-label { width: 100%; flex: none; }
}
</style>
