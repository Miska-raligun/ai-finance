<!-- components/TripRowsEditor.vue — 多字段列表的编辑(当天时间轴、景点)

     和 TripListEditor 的区别:那边一条就是一句话,一个 textarea 够用;
     这边一条有好几格(时间 / 事项 / 备注 / 重点),得逐格改。

     AI 写出来的内容一样要能改——行程单里的时间本来就常和实际对不上,
     真到了现场更是照着改。只读的行程安排是没有用的。
-->
<template>
  <section class="re">
    <div class="re-head">
      <h4 class="re-t">{{ label }}</h4>
      <button v-if="!editing" type="button" class="re-b" @click="start">
        {{ rows.length ? '✎ 编辑' : '＋ 添加' }}
      </button>
    </div>

    <slot v-if="!editing" />
    <p v-if="!editing && !rows.length" class="re-none">还没有内容</p>

    <template v-else-if="editing">
      <div v-for="(row, i) in draft" :key="i" class="re-row">
        <div class="re-line">
          <input
            v-for="f in narrow"
            :key="f.i"
            v-model="row[f.i]"
            class="re-in re-in-narrow"
            :placeholder="f.placeholder || f.label"
            :aria-label="f.label"
          >
          <button
            v-if="flagField"
            type="button"
            class="re-flag"
            :class="{ on: row[flagField.i] }"
            :title="flagField.label"
            @click="row[flagField.i] = row[flagField.i] ? 0 : 1"
          >★</button>
          <span class="re-spacer"></span>
          <button type="button" class="re-icon" title="上移" :disabled="i === 0" @click="move(i, -1)">↑</button>
          <button type="button" class="re-icon" title="下移" :disabled="i === draft.length - 1" @click="move(i, 1)">↓</button>
          <button type="button" class="re-icon danger" title="删掉这行" @click="draft.splice(i, 1)">✕</button>
        </div>
        <input
          v-for="f in wide"
          :key="f.i"
          v-model="row[f.i]"
          class="re-in"
          :placeholder="f.placeholder || f.label"
          :aria-label="f.label"
        >
      </div>

      <button type="button" class="re-b re-add" @click="add">＋ 加一行</button>

      <div class="re-foot">
        <span class="re-spacer"></span>
        <button type="button" class="re-b" @click="editing = false">取消</button>
        <button type="button" class="re-b primary" :disabled="saving" @click="save">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </div>
    </template>
  </section>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  // 每行是个数组;fields 说明第几格是什么
  // [{ i: 0, label: '时间', narrow: true, placeholder: '09:00' }, …]
  rows: { type: Array, default: () => [] },
  fields: { type: Array, required: true },
})
const emit = defineEmits(['save'])

const editing = ref(false)
const saving = ref(false)
const draft = ref([])

const narrow = computed(() => props.fields.filter(f => f.narrow && !f.flag))
const wide = computed(() => props.fields.filter(f => !f.narrow && !f.flag))
const flagField = computed(() => props.fields.find(f => f.flag) || null)

// fields 的**顺序**是界面上的排法(时间、★、事项、备注),f.i 才是它在
// 数据行里的下标。两者不一样:★ 显示在第二个,存的却是第 4 格。所以造行时
// 必须按下标铺,不能按 fields 的顺序铺——按顺序铺会把 ★ 的 0/1 塞进"事项"。
const width = computed(() => Math.max(...props.fields.map(f => f.i)) + 1)

function cell(k) {
  return props.fields.find(f => f.i === k) || null
}

function blank() {
  return Array.from({ length: width.value }, (_, k) => (cell(k)?.flag ? 0 : ''))
}

function start() {
  // 深拷贝:取消时要能原样丢掉,不能就地改了父组件手里那份
  draft.value = props.rows.map(r => Array.from({ length: width.value }, (_, k) => (
    cell(k)?.flag ? (r[k] ? 1 : 0) : (r[k] ?? '')
  )))
  if (!draft.value.length) draft.value.push(blank())
  editing.value = true
}

function add() {
  draft.value.push(blank())
}

function move(i, d) {
  const j = i + d
  if (j < 0 || j >= draft.value.length) return
  const [row] = draft.value.splice(i, 1)
  draft.value.splice(j, 0, row)
}

async function save() {
  saving.value = true
  try {
    // 整行都空的丢掉——加了一行又没填是常态,没必要存进去
    const keep = flagField.value
      ? props.fields.filter(f => !f.flag).map(f => f.i)
      : props.fields.map(f => f.i)
    const out = draft.value
      .map(r => r.map(v => (typeof v === 'string' ? v.trim() : v)))
      .filter(r => keep.some(i => String(r[i] || '').length))
    await Promise.resolve(emit('save', out))
    editing.value = false
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.re { margin-top: 16px; }
.re-head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.re-t {
  margin: 0 0 6px; font-size: 12px; font-weight: 800; letter-spacing: .08em;
  color: var(--trip-ink-2, var(--color-text-muted));
}
.re-none { margin: 0; font-size: 12px; color: var(--color-text-muted); }

.re-row {
  border: 1px solid var(--color-border-light); border-radius: 10px;
  padding: 8px; margin-bottom: 8px; display: flex; flex-direction: column; gap: 6px;
}
.re-line { display: flex; align-items: center; gap: 6px; }
.re-spacer { flex: 1; }
.re-in {
  width: 100%; box-sizing: border-box; font: inherit; font-size: 13px;
  border: 1px solid var(--color-border-light); border-radius: 8px; padding: 6px 8px;
  background: var(--color-surface); color: var(--color-text);
}
.re-in:focus { outline: none; border-color: var(--trip-accent, var(--color-primary)); }
/* 时间这种格子固定窄一点,不然一行里它会把事项挤没 */
.re-in-narrow { width: 5.5em; flex: 0 0 auto; font-variant-numeric: tabular-nums; }

.re-icon, .re-flag {
  appearance: none; border: 1px solid var(--color-border-light);
  background: var(--color-surface); color: var(--color-text-muted);
  font: inherit; font-size: 12px; line-height: 1;
  width: 28px; height: 28px; border-radius: 8px; cursor: pointer; flex: 0 0 auto;
}
.re-icon:disabled { opacity: .35; cursor: default; }
.re-icon.danger { color: var(--color-error, #e05a5a); }
.re-flag.on {
  color: var(--trip-accent, var(--color-primary));
  border-color: currentColor; font-weight: 700;
}

.re-b {
  appearance: none; border: 1px solid var(--color-border-light); background: var(--color-surface);
  color: var(--color-text-muted); font: inherit; font-size: 11.5px;
  padding: 3px 12px; border-radius: 999px; cursor: pointer;
}
.re-b:disabled { opacity: .55; cursor: default; }
.re-b.primary {
  background: var(--trip-accent, var(--color-primary));
  border-color: var(--trip-accent, var(--color-primary)); color: #fff; font-weight: 700;
}
.re-add { width: 100%; padding: 6px; border-style: dashed; }
.re-foot { display: flex; align-items: center; gap: 8px; margin-top: 10px; }
</style>
