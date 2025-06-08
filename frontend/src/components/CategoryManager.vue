<!-- src/components/CategoryManager.vue -->
<template>
  <el-card>
    <template #header>📁 分类管理</template>
    <div>
      <el-input v-model="newCategory" placeholder="新分类" style="width: 70%;" />
      <el-button type="primary" @click="addCategory">添加</el-button>
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
import axios from 'axios'
const props = defineProps({ refreshFlag: Number })

const categories = ref([])
const newCategory = ref('')

async function fetchCategories() {
  const res = await axios.get('/categories')
  categories.value = res.data
}

async function addCategory() {
  if (!newCategory.value) return
  await axios.post('/categories', { name: newCategory.value })
  newCategory.value = ''
  await fetchCategories()
}

async function deleteCategory(name) {
  await axios.delete(`/categories/${encodeURIComponent(name)}`)
  await fetchCategories()
}

onMounted(fetchCategories)
watch(() => props.refreshFlag, fetchCategories)
</script>



