<!-- src/components/CategoryManager.vue -->
<template>
  <div class="category-manager">
    <div class="input-row">
      <el-input v-model="newCategory" placeholder="输入新分类名称" size="small" style="flex: 1" @keyup.enter="addCategory" />
      <el-button type="primary" size="small" @click="addCategory">添加</el-button>
    </div>
    <div class="tags-wrap">
      <el-tag
        v-for="item in categories"
        :key="item.name"
        closable
        size="default"
        class="cat-tag"
        @close="deleteCategory(item.name)"
      >
        {{ item.name }}
      </el-tag>
      <span v-if="!categories.length" class="empty-tip">暂无分类，请添加</span>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
const emit = defineEmits(['refresh'])
import api from '@/api'
const props = defineProps({
  refreshFlag: Number,
  type: { type: String, default: 'expense' }
})

const categories = ref([])
const newCategory = ref('')

async function fetchCategories() {
  const res = await api.get('/api/categories', { params: { type: props.type } })
  categories.value = res.data
}

async function addCategory() {
  if (!newCategory.value) return
  await api.post('/api/categories', {
    name: newCategory.value,
    type: props.type === 'income' ? '收入' : '支出'
  })
  newCategory.value = ''
  await fetchCategories()
  emit('refresh')
}

async function deleteCategory(name) {
  try {
    await api.delete(`/api/categories/${encodeURIComponent(name)}`)
    await fetchCategories()
    emit('refresh')
  } catch (e) {
    const msg = e.response?.data?.error || '删除失败，请稍后重试'
    ElMessage.error(msg)
  }
}

onMounted(fetchCategories)
watch([() => props.refreshFlag, () => props.type], fetchCategories)
</script>

<style scoped>
.category-manager {
  padding: 4px 0;
}
.input-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}
.tags-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 32px;
}
.cat-tag {
  background: var(--color-primary-light) !important;
  color: var(--color-primary) !important;
  border-color: rgba(79,70,229,0.2) !important;
  font-weight: 500;
  border-radius: 6px !important;
}
.cat-tag :deep(.el-tag__close) {
  color: var(--color-primary) !important;
}
.cat-tag :deep(.el-tag__close):hover {
  background: rgba(79,70,229,0.15) !important;
}
.empty-tip {
  font-size: 13px;
  color: var(--color-text-muted);
}

@media (max-width: 768px) {
  .input-row { flex-direction: column; align-items: stretch; }
}
</style>
