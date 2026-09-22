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
            :key="fid(f)"
            v-model="row.cells[fid(f)]"
            class="re-in re-in-narrow"
            :placeholder="f.placeholder || f.label"
            :aria-label="f.label"
          >
          <button
            v-if="flagField"
            type="button"
            class="re-flag"
            :class="{ on: row.cells[fid(flagField)] }"
            :title="flagField.label"
            @click="row.cells[fid(flagField)] = row.cells[fid(flagField)] ? 0 : 1"
          >★</button>
          <!-- 有坐标的行标出来:改名字不会丢掉这个点在地图上的位置 -->
          <span v-if="pinned(row)" class="re-pin" title="这个地点在地图上">📍</span>
          <span class="re-spacer"></span>
          <button type="button" class="re-icon" title="上移" :disabled="i === 0" @click="move(i, -1)">↑</button>
          <button type="button" class="re-icon" title="下移" :disabled="i === draft.length - 1" @click="move(i, 1)">↓</button>
          <button type="button" class="re-icon danger" title="删掉这行" @click="draft.splice(i, 1)">✕</button>
        </div>
        <input
          v-for="f in wide"
          :key="fid(f)"
          v-model="row.cells[fid(f)]"
          class="re-in"
          :placeholder="f.placeholder || f.label"
          :aria-label="f.label"
        >
      </div>

      <button type="button" class="re-b re-add" @click="add">＋ 加一行</button>
      <p v-if="hint" class="re-hint">{{ hint }}</p>

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
  rows: { type: Array, default: () => [] },
  // 每个字段要么给 i(行是数组,i 是下标),要么给 k(行是对象,k 是键名):
  //   [{ i: 0, label: '时间', narrow: true }, { i: 3, label: '重点', flag: true }]
  //   [{ k: 't', label: '名称' }, { k: 'dur', label: '时长', narrow: true }]
  fields: { type: Array, required: true },
  hint: { type: String, default: '' },
})
const emit = defineEmits(['save'])

const editing = ref(false)
const saving = ref(false)
// 每行是 { src, cells }:src 是原来那条(对象模式下要把没编辑的字段原样带回去
// ——坐标、介绍、照片都挂在上面,丢了就是灾难),cells 是这次改的几格
const draft = ref([])

const objectMode = computed(() => props.fields.some(f => f.k !== undefined))
function fid(f) { return f.k !== undefined ? f.k : f.i }

const narrow = computed(() => props.fields.filter(f => f.narrow && !f.flag))
const wide = computed(() => props.fields.filter(f => !f.narrow && !f.flag))
const flagField = computed(() => props.fields.find(f => f.flag) || null)

/** 这一行原来有没有坐标。只做提示用,不参与保存。 */
function pinned(row) {
  const s = row.src
  return !!(s && !Array.isArray(s) && isFinite(Number(s.lat)) && isFinite(Number(s.lng)))
}

function read(src, f) {
  const v = src == null ? undefined : src[fid(f)]
  return f.flag ? (v ? 1 : 0) : (v ?? '')
}

function makeRow(src) {
  const cells = {}
  for (const f of props.fields) cells[fid(f)] = read(src, f)
  // src 只在对象模式下有用(要把没编辑的字段带回去);数组模式下不需要
  return { src: objectMode.value ? src : null, cells }
}

function start() {
  // 不就地改父组件手里那份:取消时要能原样丢掉
  draft.value = props.rows.map(makeRow)
  if (!draft.value.length) draft.value.push(makeRow(null))
  editing.value = true
}

function add() {
  draft.value.push(makeRow(null))
}

function move(i, d) {
  const j = i + d
  if (j < 0 || j >= draft.value.length) return
  const [row] = draft.value.splice(i, 1)
  draft.value.splice(j, 0, row)
}

/** fields 的**顺序**是界面上的排法(时间、★、事项、备注),f.i 才是它在
 *  数据行里的下标。两者不一样:★ 显示在第二个,存的却是第 4 格。所以铺
 *  数组时必须按下标铺,不能按 fields 的顺序铺。 */
function toArray(cells) {
  const width = Math.max(...props.fields.map(f => f.i)) + 1
  return Array.from({ length: width }, (_, i) => {
    const f = props.fields.find(x => x.i === i)
    if (!f) return ''
    return f.flag ? (cells[i] ? 1 : 0) : cells[i]
  })
}

/** 对象模式:原来那条原样带回去,只覆盖编辑过的几个键。
 *  空字符串等于"没有这个字段",删掉而不是存个空串。 */
function toObject(row) {
  const out = { ...(row.src || {}) }
  for (const f of props.fields) {
    const v = row.cells[fid(f)]
    if (f.flag) {
      if (v) out[fid(f)] = 1
      else delete out[fid(f)]
    } else if (String(v ?? '').length) {
      out[fid(f)] = v
    } else {
      delete out[fid(f)]
    }
  }
  return out
}

async function save() {
  saving.value = true
  try {
    const text = props.fields.filter(f => !f.flag)
    const out = draft.value
      .map(r => {
        const cells = {}
        for (const k in r.cells) {
          const v = r.cells[k]
          cells[k] = typeof v === 'string' ? v.trim() : v
        }
        return { src: r.src, cells }
      })
      // 文字格全空的丢掉——加了一行又没填是常态,没必要存进去
      .filter(r => text.some(f => String(r.cells[fid(f)] || '').length))
      .map(r => (objectMode.value ? toObject(r) : toArray(r.cells)))
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
.re-hint { margin: 8px 0 0; font-size: 11.5px; color: var(--color-text-muted); line-height: 1.6; }
.re-pin { font-size: 12px; flex: 0 0 auto; }
.re-foot { display: flex; align-items: center; gap: 8px; margin-top: 10px; }
</style>
