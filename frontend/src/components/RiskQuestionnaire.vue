<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <span>🎚 风险偏好测评</span>
        <el-tag v-if="profile" :type="tagType(profile.level)">{{ levelLabel(profile.level) }}</el-tag>
      </div>
    </template>

    <div v-if="profile && !editing" class="profile">
      <div class="profile-row"><span>测评得分：</span><strong>{{ profile.score }}</strong></div>
      <div class="profile-row"><span>风险等级：</span><strong>{{ levelLabel(profile.level) }}</strong></div>
      <div v-if="profile.summary" class="summary">{{ profile.summary }}</div>
      <el-button size="small" @click="editing = true">重新测评</el-button>
    </div>

    <div v-else>
      <div v-if="loading && !questions.length" class="empty">加载中…</div>
      <el-form v-else label-position="top">
        <el-form-item v-for="q in questions" :key="q.id" :label="q.text">
          <el-radio-group v-model="answers[q.id]">
            <el-radio
              v-for="opt in q.options"
              :key="opt.value"
              :value="opt.value"
            >
              {{ opt.label }}
            </el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <div class="form-footer">
        <el-button v-if="profile" @click="editing = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">提交测评</el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useInvestmentStore } from '@/stores/investment'
import { useUserStore } from '@/stores/user'

const store = useInvestmentStore()
const userStore = useUserStore()

const questions = ref([])
const answers = reactive({})
const profile = ref(null)
const loading = ref(false)
const submitting = ref(false)
const editing = ref(false)

const LEVEL_LABEL = {
  conservative: '保守型', balanced: '平衡型', aggressive: '激进型',
}
function levelLabel(l) { return LEVEL_LABEL[l] || l || '未测评' }
function tagType(l) {
  return l === 'aggressive' ? 'danger' : l === 'balanced' ? 'warning' : 'success'
}

async function load() {
  loading.value = true
  try {
    const data = await store.fetchRiskQuiz()
    questions.value = data.questions || []
    profile.value = data.profile || null
    editing.value = !profile.value
  } finally {
    loading.value = false
  }
}

async function submit() {
  // 必须五题都答
  for (const q of questions.value) {
    if (!answers[q.id]) {
      ElMessage.warning('请回答所有问题')
      return
    }
  }
  submitting.value = true
  try {
    const result = await store.submitRiskQuiz({ ...answers }, userStore.llmPayload)
    profile.value = result
    editing.value = false
    ElMessage.success(`测评完成，你是「${levelLabel(result.level)}」`)
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '测评失败')
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.header-row {
  display: flex; justify-content: space-between; align-items: center; width: 100%;
}
.profile {
  display: flex; flex-direction: column; gap: 10px;
}
.profile-row {
  font-size: 14px; color: var(--color-text);
}
.profile-row strong {
  margin-left: 6px; color: var(--color-primary);
}
.summary {
  font-size: 13px;
  color: var(--color-text-muted);
  padding: 10px 12px;
  background: #F0F7FF;
  border-radius: 8px;
  line-height: 1.6;
}
.empty {
  text-align: center; color: var(--color-text-muted); padding: 24px 0;
}
.form-footer {
  display: flex; justify-content: flex-end; gap: 8px;
}
.el-radio-group {
  display: flex; flex-direction: column; align-items: flex-start; gap: 6px;
}
</style>
