<!-- components/TripFacts.vue — 速查:领队/使馆电话、航班、时差、硬规定等
     body 是纯文本(保留换行);电话号码自动识别成 tel: 链接,手机上可直接拨。
     每条可单独决定是否出现在公开分享页,默认不公开。 -->
<template>
  <div class="fx">
    <el-empty v-if="!facts.length && !readonly" description="还没有速查信息，加一条（如 领队 / 使馆电话 / 航班）" :image-size="60" />

    <section v-for="f in facts" :key="f.id || f.label" class="fx-item">
      <div class="fx-head">
        <h4 class="fx-label">{{ f.label }}</h4>
        <div v-if="!readonly" class="fx-actions">
          <el-tooltip :content="f.is_public ? '会出现在分享页' : '仅自己可见'" placement="top">
            <button class="fx-eye" :class="{ on: f.is_public }" @click="togglePublic(f)">
              {{ f.is_public ? '🔗 已公开' : '🔒 私密' }}
            </button>
          </el-tooltip>
          <button class="fx-x" title="删除" @click="remove(f)">×</button>
        </div>
      </div>
      <!-- eslint-disable-next-line vue/no-v-html -- linkifyPhones 已做 HTML 转义 -->
      <div class="fx-body" v-html="linkifyPhones(f.body || '')"></div>
    </section>

    <div v-if="!readonly" class="fx-ai">
      <button type="button" class="fx-ai-b" :disabled="ai.state.running" @click="propose">
        <span v-if="ai.state.running" class="fx-spin" aria-hidden="true"></span>
        {{ ai.state.running ? `生成中… ${ai.elapsed.value}s` : '✨ 让 AI 补几条(时差 / 货币 / 插头…)' }}
      </button>
      <span v-if="ai.state.running" class="fx-ai-err">要十几秒,切到别的页面也不会断</span>
      <span v-if="aiErr" class="fx-ai-err">{{ aiErr }}</span>
    </div>

    <!-- AI 出的是建议:逐条挑,挑中的才入库。加进来同样默认私密。 -->
    <div v-if="!readonly && proposed.length" class="fx-prop">
      <div class="fx-prop-h">
        <span>AI 建议 {{ picked.size }} / {{ proposed.length }}</span>
        <button type="button" class="fx-ai-b" @click="proposed = []">丢弃</button>
        <button
          type="button"
          class="fx-ai-b primary"
          :disabled="!picked.size || adding"
          @click="acceptPicked"
        >{{ adding ? '加入中…' : `加入选中的 ${picked.size} 条` }}</button>
      </div>
      <label v-for="(it, i) in proposed" :key="i" class="fx-prop-i" :class="{ on: picked.has(i) }">
        <input type="checkbox" :checked="picked.has(i)" @change="togglePick(i)">
        <span class="fx-prop-t">
          <b>{{ it.label }}</b>
          <span>{{ it.body }}</span>
        </span>
      </label>
    </div>

    <div v-if="!readonly" class="fx-add">
      <el-input v-model="draft.label" size="small" placeholder="标题（如 中国使馆）" class="fx-in-label" />
      <el-input
        v-model="draft.body"
        type="textarea"
        :rows="3"
        placeholder="内容，可多行。电话会自动变成可拨号链接。"
      />
      <div class="fx-add-foot">
        <label class="fx-pub-check">
          <input type="checkbox" v-model="draft.is_public">
          <span>在分享页显示</span>
        </label>
        <el-button size="small" type="primary" :loading="saving" @click="add">添加</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useAiBlock, runAiBlock, clearAiBlock } from '@/utils/aiBlocks'
import { ElMessage } from 'element-plus'
import api from '@/api'

const props = defineProps({
  tripId: { type: Number, default: 0 },
  facts: { type: Array, default: () => [] },
  readonly: { type: Boolean, default: false },   // 公开分享页用只读模式
})
const emit = defineEmits(['changed'])

const saving = ref(false)
const draft = reactive({ label: '', body: '', is_public: false })

// AI 建议:先摆出来让人挑,挑中的才入库。
// 在途状态放模块级 store,切走再回来还能接上(见 utils/aiBlocks.js)
const adding = ref(false)
const proposed = ref([])
const picked = ref(new Set())
const localErr = ref('')
const aiKey = `facts:${props.tripId}`
const ai = useAiBlock(aiKey)
const aiErr = computed(() => ai.state.error || localErr.value)

function absorb() {
  const data = ai.state.result
  if (!data) return
  const have = new Set(props.facts.map(f => f.label))
  proposed.value = (data.items || []).filter(x => !have.has(x.label))
  picked.value = new Set(proposed.value.map((_, i) => i))
  localErr.value = proposed.value.length ? '' : 'AI 想到的都已经在速查里了'
  clearAiBlock(aiKey)
}
watch(() => ai.state.result, absorb)
onMounted(absorb)

async function propose() {
  localErr.value = ''
  await runAiBlock(aiKey, `/api/trips/${props.tripId}/ai/block`, { kind: 'facts' })
}

function togglePick(i) {
  const s = new Set(picked.value)
  s.has(i) ? s.delete(i) : s.add(i)
  picked.value = s
}

async function acceptPicked() {
  adding.value = true
  try {
    let n = props.facts.length
    for (let i = 0; i < proposed.value.length; i++) {
      if (!picked.value.has(i)) continue
      const it = proposed.value[i]
      // is_public 不传,后端默认私密——AI 写的也要自己过目了再公开
      await api.post(`/api/trips/${props.tripId}/facts`, {
        label: it.label, body: it.body, sort_order: n++,
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

/** 先整体 HTML 转义,再把电话号码替换成 tel: 链接——顺序不能反,
 *  否则用户输入的内容会变成可执行 HTML。 */
function linkifyPhones(text) {
  const esc = String(text)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
  // 匹配 +358-9-0400618582 / 13945079235 / +46 8 57936404 这类
  return esc.replace(/(\+?\d[\d\s\-]{6,18}\d)/g, (m) => {
    const dial = m.replace(/[\s\-]/g, '')
    return `<a class="fx-tel" href="tel:${dial}">${m}</a>`
  })
}

async function add() {
  if (!draft.label.trim()) { ElMessage.warning('填一下标题'); return }
  saving.value = true
  try {
    await api.post(`/api/trips/${props.tripId}/facts`, {
      label: draft.label, body: draft.body, is_public: draft.is_public,
      sort_order: props.facts.length,
    })
    draft.label = ''; draft.body = ''; draft.is_public = false
    emit('changed')
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || '添加失败')
  } finally {
    saving.value = false
  }
}

async function togglePublic(f) {
  const next = f.is_public ? 0 : 1
  try {
    await api.patch(`/api/trips/${props.tripId}/facts/${f.id}`, { is_public: !!next })
    f.is_public = next
    ElMessage.success(next ? '这条会出现在分享页' : '已设为仅自己可见')
  } catch {
    ElMessage.error('保存失败')
  }
}

async function remove(f) {
  try {
    await api.delete(`/api/trips/${props.tripId}/facts/${f.id}`)
    emit('changed')
  } catch {
    ElMessage.error('删除失败')
  }
}
</script>

<style scoped>
.fx-ai { display: flex; align-items: center; gap: 10px; margin-top: 14px; flex-wrap: wrap; }
.fx-ai-b {
  appearance: none; border: 1px solid var(--trip-accent, var(--color-primary));
  background: var(--color-surface); color: var(--trip-accent, var(--color-primary));
  font: inherit; font-size: 12px; padding: 3px 12px; border-radius: 999px; cursor: pointer;
}
.fx-ai-b:disabled { opacity: .55; cursor: default; }
.fx-ai-b.primary { background: var(--trip-accent, var(--color-primary)); color: #fff; font-weight: 700; }
.fx-ai-err { font-size: 12px; color: var(--color-text-muted); }
.fx-spin {
  display: inline-block; width: 10px; height: 10px; margin-right: 5px;
  vertical-align: -1px; border-radius: 50%;
  border: 2px solid currentColor; border-top-color: transparent;
  animation: fx-rot .7s linear infinite;
}
@keyframes fx-rot { to { transform: rotate(360deg); } }
.fx-prop {
  border: 1px dashed var(--trip-accent, var(--color-primary));
  border-radius: 12px; padding: 10px 12px; margin-top: 10px;
}
.fx-prop-h {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  font-size: 12px; color: var(--color-text-muted); margin-bottom: 8px;
}
.fx-prop-h span { margin-right: auto; }
.fx-prop-i { display: flex; align-items: flex-start; gap: 8px; padding: 4px 0; cursor: pointer; opacity: .55; }
.fx-prop-i.on { opacity: 1; }
.fx-prop-t { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.fx-prop-t b { font-size: 12.5px; }
.fx-prop-t span { font-size: 12px; color: var(--color-text-muted); white-space: pre-wrap; }

.fx-item { padding: 10px 0; border-bottom: 1px solid var(--trip-line, var(--color-border-light)); }
.fx-item:last-of-type { border-bottom: none; }
.fx-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.fx-label { margin: 0; font-size: 12px; font-weight: 800; letter-spacing: .06em; color: var(--trip-ink-2, var(--color-text-muted)); }
.fx-actions { display: flex; align-items: center; gap: 6px; }
.fx-eye {
  border: 1px solid var(--color-border-light); background: var(--color-surface);
  color: var(--color-text-muted); font: inherit; font-size: 11px;
  padding: 1px 8px; border-radius: 999px; cursor: pointer;
}
.fx-eye.on { background: var(--trip-accent, var(--color-primary)); border-color: var(--trip-accent, var(--color-primary)); color: #fff; }
.fx-x { border: 0; background: none; cursor: pointer; color: var(--color-text-muted); font-size: 16px; line-height: 1; }
.fx-x:hover { color: var(--color-error, #e05a5a); }

.fx-body {
  margin-top: 4px; font-size: 13px; line-height: 1.7;
  white-space: pre-wrap; word-break: break-word; color: var(--color-text);
}
.fx-body :deep(.fx-tel) {
  color: var(--trip-accent, var(--color-primary));
  font-weight: 600; text-decoration: none;
  border-bottom: 1px dashed currentColor;
}

.fx-add { margin-top: 16px; display: flex; flex-direction: column; gap: 8px; }
.fx-add-foot { display: flex; align-items: center; justify-content: space-between; }
.fx-pub-check { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--color-text-muted); cursor: pointer; }
.fx-pub-check input { accent-color: var(--trip-accent, var(--color-primary)); }
</style>
