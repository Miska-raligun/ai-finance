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
import { ref, reactive } from 'vue'
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
