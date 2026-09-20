<!-- components/TripPacking.vue — 打包清单:按分组勾选,进度入库(多端同步) -->
<template>
  <div class="pk">
    <div class="pk-prog">
      <span class="pk-prog-label">已备</span>
      <span class="pk-bar"><i :style="{ width: pct + '%' }" /></span>
      <span class="pk-count">{{ checkedCount }} / {{ items.length }}</span>
    </div>

    <el-empty v-if="!items.length" description="还没有打包清单，在下面加第一条" :image-size="60" />

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
import { ref, reactive, computed } from 'vue'
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
