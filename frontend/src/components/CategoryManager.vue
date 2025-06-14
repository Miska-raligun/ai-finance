<!-- src/components/CategoryManager.vue -->
<template>
  <el-card>
    <template #header>📁 分类管理</template>
    <div class="input-row">
      <el-input v-model="newCategory" placeholder="新分类" style="flex: 1" />
      <el-button type="primary" size="small" @click="addCategory">添加</el-button>
    </div>
    <el-tag
      v-for="item in categories"
      :key="item.name"
      closable
      @close="deleteCategory(item.name)"
      style="margin: 5px"
    >
      {{ item.name }}
    </el-tag>
  </el-card>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
const emit = defineEmits(['refresh'])
import api from '@/api'
const props = defineProps({
  refreshFlag: Number,
  type: { type: String, default: 'expense' } // 'expense' or 'income'
})

const categories = ref([])
const newCategory = ref('')

async function fetchCategories() {
  const res = await api.get('/api/categories', {
    params: { type: props.type }
  })
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
  await api.delete(`/api/categories/${encodeURIComponent(name)}`)
  await fetchCategories()
  emit('refresh')
}

onMounted(fetchCategories)
watch([() => props.refreshFlag, () => props.type], fetchCategories)
</script>

<style scoped>
.input-row {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
@media (max-width: 600px) {
  .input-row {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>


