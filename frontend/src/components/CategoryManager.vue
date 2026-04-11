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
import { computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { ref } from 'vue'
import { useCategoryStore } from '@/stores/categories'

const props = defineProps({
  type: { type: String, default: 'expense' }
})

const categoryStore = useCategoryStore()
// 分类列表从 store 派生，新增/删除后自动响应
const categories = computed(() =>
  props.type === 'expense' ? categoryStore.expense : categoryStore.income
)
const newCategory = ref('')

async function addCategory() {
  if (!newCategory.value) return
  try {
    await categoryStore.addCategory(newCategory.value, props.type)
    newCategory.value = ''
  } catch (e) {
    const msg = e.response?.data?.error || '添加失败，请稍后重试'
    ElMessage.error(msg)
  }
}

async function deleteCategory(name) {
  try {
    await categoryStore.deleteCategory(name, props.type)
  } catch (e) {
    const msg = e.response?.data?.error || '删除失败，请稍后重试'
    ElMessage.error(msg)
  }
}

onMounted(() => categoryStore.fetchCategories(props.type))
watch(() => props.type, (t) => categoryStore.fetchCategories(t))
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
