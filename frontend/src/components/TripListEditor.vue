<!-- components/TripListEditor.vue — 一组短句的展示 + 编辑 + AI 起草

     贴士 / 拍摄建议 / 买什么 / 注意 都是这种结构。编辑用「一行一条」的
     textarea,比一堆行内输入框好使,也好整段粘贴。

     AI 只负责把草稿填进编辑框,**保存与否由人决定**——不会直接盖掉已有内容。 -->
<template>
  <section v-if="items.length || canEdit" class="le">
    <div class="le-head">
      <h4 class="le-t">{{ label }}</h4>
      <div v-if="canEdit" class="le-act">
        <button v-if="!editing" type="button" class="le-b" @click="start">
          {{ items.length ? '✎ 编辑' : '＋ 添加' }}
        </button>
        <button
          v-if="!editing && aiKind"
          type="button"
          class="le-b le-ai"
          :disabled="ai.state.running"
          @click="generate(true)"
        >
          <span v-if="ai.state.running" class="le-spin" aria-hidden="true"></span>
          {{ ai.state.running ? `${ai.elapsed.value}s` : '✨ AI 起草' }}
        </button>
      </div>
    </div>

    <ul v-if="!editing && items.length" class="le-list">
      <li v-for="(t, i) in items" :key="i">{{ t }}</li>
    </ul>
    <p v-else-if="!editing" class="le-none">还没有内容</p>

    <template v-else>
      <textarea
        v-model="draft"
        class="le-edit"
        :rows="Math.min(10, Math.max(3, draft.split('\n').length + 1))"
        placeholder="一行一条"
      ></textarea>
      <div class="le-foot">
        <button
          v-if="aiKind"
          type="button"
          class="le-b le-ai"
          :disabled="ai.state.running"
          @click="generate(false)"
        >
          <span v-if="ai.state.running" class="le-spin" aria-hidden="true"></span>
          {{ ai.state.running ? `生成中… ${ai.elapsed.value}s` : '✨ 让 AI 补几条' }}
        </button>
        <span class="le-spacer"></span>
        <button type="button" class="le-b" @click="editing = false">取消</button>
        <button type="button" class="le-b primary" :disabled="saving" @click="save">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </div>
      <p v-if="err" class="le-err">{{ err }}</p>
    </template>
  </section>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import api from '@/api'
import { useAiBlock, runAiBlock, clearAiBlock } from '@/utils/aiJobs'

const props = defineProps({
  items: { type: Array, default: () => [] },
  label: { type: String, required: true },
  canEdit: { type: Boolean, default: false },
  // AI 起草需要的上下文;不给 aiKind 就只有手动编辑
  aiKind: { type: String, default: '' },
  tripId: { type: Number, default: 0 },
  dayNo: { type: Number, default: 0 },
})
const emit = defineEmits(['save'])

const editing = ref(false)
const draft = ref('')
const saving = ref(false)
const localErr = ref('')
// 在途状态放模块级 store:切走再回来、弹窗关了再开都还在
const aiKey = computed(() => `${props.aiKind}:${props.tripId}:${props.dayNo}`)
const ai = useAiBlock(aiKey.value)
const err = computed(() => ai.state.error || localErr.value)

function start() {
  draft.value = props.items.join('\n')
  localErr.value = ''
  editing.value = true
}

/** store 里有结果就并进草稿(去重),并打开编辑框等人改。 */
function absorb() {
  const data = ai.state.result
  if (!data) return
  const lines = (editing.value ? draft.value : props.items.join('\n'))
    .split('\n').map(x => x.trim()).filter(Boolean)
  for (const x of (data.items || [])) if (!lines.includes(x)) lines.push(x)
  draft.value = lines.join('\n')
  editing.value = true
  clearAiBlock(aiKey.value)
}
watch(() => ai.state.result, absorb)
onMounted(absorb)

async function save() {
  localErr.value = ''
  saving.value = true
  try {
    const next = draft.value.split('\n').map(x => x.trim()).filter(Boolean)
    await Promise.resolve(emit('save', next))
    editing.value = false
  } finally {
    saving.value = false
  }
}

/** AI 出的是草稿,填进编辑框等人改。结果由 absorb() 接手。 */
async function generate(openEditor) {
  if (!props.aiKind || !props.tripId) return
  localErr.value = ''
  if (openEditor && !editing.value) {
    draft.value = props.items.join('\n')
    editing.value = true        // 先把编辑框开出来,好让人看见在跑
  }
  await runAiBlock(aiKey.value, `/api/trips/${props.tripId}/ai/block`, {
    kind: props.aiKind,
    day_no: props.dayNo || undefined,
  })
}
</script>

<style scoped>
.le { margin-top: 16px; }
.le-head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.le-t {
  margin: 0 0 6px; font-size: 12px; font-weight: 800; letter-spacing: .08em;
  color: var(--trip-ink-2, var(--color-text-muted));
}
.le-act { display: flex; gap: 8px; flex-shrink: 0; }
.le-b {
  appearance: none; border: 1px solid var(--color-border-light); background: var(--color-surface);
  color: var(--color-text-muted); font: inherit; font-size: 11.5px;
  padding: 2px 10px; border-radius: 999px; cursor: pointer;
}
.le-b:disabled { opacity: .55; cursor: default; }
.le-b.le-ai { color: var(--trip-accent, var(--color-primary)); border-color: currentColor; }
.le-b.primary {
  background: var(--trip-accent, var(--color-primary));
  border-color: var(--trip-accent, var(--color-primary)); color: #fff; font-weight: 700;
}
.le-list { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.7; }
.le-none { margin: 0; font-size: 12px; color: var(--color-text-muted); }
.le-edit {
  width: 100%; box-sizing: border-box; font: inherit; font-size: 13px; line-height: 1.7;
  border: 1px solid var(--color-border-light); border-radius: 10px; padding: 8px 10px;
  resize: vertical; background: var(--color-surface); color: var(--color-text);
}
.le-edit:focus { outline: none; border-color: var(--trip-accent, var(--color-primary)); }
.le-foot { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.le-spacer { flex: 1; }
.le-err { margin: 6px 0 0; font-size: 12px; color: var(--color-error, #e05a5a); }
.le-spin {
  display: inline-block; width: 9px; height: 9px; margin-right: 4px;
  vertical-align: -1px; border-radius: 50%;
  border: 2px solid currentColor; border-top-color: transparent;
  animation: le-rot .7s linear infinite;
}
@keyframes le-rot { to { transform: rotate(360deg); } }
</style>
