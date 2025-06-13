<template>
  <el-card>
    <template #header>🛠 用户管理</template>
    <el-table :data="users" stripe border @selection-change="onSelect">
      <el-table-column type="selection" width="55" />
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="username" label="用户名" />
      <el-table-column prop="is_admin" label="管理员" width="80">
        <template #default="scope">
          <span>{{ scope.row.is_admin ? '是' : '否' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="scope">
          <el-button size="small" @click="changePwd(scope.row)">改密</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-button type="danger" style="margin-top:10px" @click="deleteSelected" :disabled="!selected.length">
      删除所选
    </el-button>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/api'
import { ElMessageBox, ElMessage } from 'element-plus'

const users = ref([])
const selected = ref([])

function onSelect(val) {
  selected.value = val
}

async function fetchUsers() {
  const res = await api.get('/api/users')
  users.value = res.data
}

async function changePwd(row) {
  try {
    const { value, action } = await ElMessageBox.prompt('输入新密码', '修改密码', {
      inputType: 'password',
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    })
    if (action !== 'confirm') return
    await api.put(`/api/users/${row.id}/password`, { password: value })
    ElMessage.success('密码已修改')
  } catch {}
}

async function deleteSelected() {
  const ids = selected.value.map(u => u.id)
  await api.post('/api/users/batch_delete', { user_ids: ids })
  selected.value = []
  fetchUsers()
}

onMounted(fetchUsers)
</script>

<style scoped>
</style>
