<template>
  <div class="admin-page">
    <el-card>
      <template #header>
        <div class="usage-header">
          <span>📊 LLM 用量看板</span>
          <el-radio-group v-model="usageRange" size="small" @change="fetchUsage">
            <el-radio-button label="7d">7 天</el-radio-button>
            <el-radio-button label="30d">30 天</el-radio-button>
            <el-radio-button label="all">全部</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <el-skeleton v-if="usageLoading" :rows="3" animated />
      <template v-else>
        <div class="usage-kpis">
          <div class="usage-kpi">
            <div class="k-label">调用次数</div>
            <div class="k-value">{{ usage.summary?.calls ?? 0 }}</div>
          </div>
          <div class="usage-kpi">
            <div class="k-label">Token 总量</div>
            <div class="k-value">{{ (usage.summary?.total_tokens ?? 0).toLocaleString() }}</div>
          </div>
        </div>
        <el-table :data="usage.rows || []" size="small" max-height="320" style="margin-top: 12px">
          <el-table-column prop="day" label="日期" width="110" />
          <el-table-column prop="endpoint" label="端点" />
          <el-table-column prop="model" label="模型" min-width="140" />
          <el-table-column prop="calls" label="次数" width="70" align="right" />
          <el-table-column prop="prompt_tokens" label="输入 T" width="90" align="right" />
          <el-table-column prop="completion_tokens" label="输出 T" width="90" align="right" />
          <el-table-column prop="total_tokens" label="总 T" width="90" align="right" />
        </el-table>
      </template>
    </el-card>

    <el-card style="margin-top: 16px">
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
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated } from 'vue'
import api from '@/api'
import { ElMessageBox, ElMessage } from 'element-plus'

const users = ref([])
const selected = ref([])
const usage = ref({ summary: {}, rows: [] })
const usageRange = ref('7d')
const usageLoading = ref(false)

async function fetchUsage() {
  usageLoading.value = true
  try {
    const res = await api.get('/api/admin/llm-usage', { params: { range: usageRange.value } })
    usage.value = res.data
  } catch (e) {
    ElMessage.error('加载 LLM 用量失败')
  } finally {
    usageLoading.value = false
  }
}

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

onMounted(() => { fetchUsers(); fetchUsage() })
onActivated(() => { fetchUsers(); fetchUsage() })
</script>

<style scoped>
.admin-page { display: flex; flex-direction: column; padding: 18px; }
.usage-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}
.usage-kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}
.usage-kpi {
  background: var(--color-bg-soft, #F8FAFC);
  border: 1px solid var(--color-border, #E5E7EB);
  border-radius: 10px;
  padding: 10px 14px;
}
.k-label { font-size: 12px; color: var(--color-text-muted, #94A3B8); }
.k-value { font-size: 22px; font-weight: 600; color: var(--color-primary, #3B82F6); }
</style>
