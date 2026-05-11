<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <span>🎚 风险偏好测评</span>
        <el-tag v-if="profile" :type="tagType(profile.level)">{{ levelLabel(profile.level) }}</el-tag>
      </div>
    </template>

    <el-alert
      v-if="!editing"
      :closable="false"
      type="info"
      class="rule-alert"
    >
      <template #title>评分规则</template>
      5 题 × 每题 1-5 分 = 合计 {{ maxScore }} 分，得分越高风险承受力越高。<br />
      <span v-for="(range, key) in thresholds" :key="key" class="threshold-pill">
        {{ range[0] }}-{{ range[1] }} → {{ levelLabel(key) }}
      </span>
    </el-alert>

    <div v-if="profile && !editing" class="profile">
      <div class="score-display">
        <div class="score-num">
          <strong>{{ profile.score }}</strong>
          <span class="score-denom">/ {{ maxScore }}</span>
        </div>
        <div class="score-level">
          <span>风险等级：</span>
          <strong :class="'level-' + profile.level">{{ levelLabel(profile.level) }}</strong>
        </div>
      </div>

      <!-- 水平分档进度条 -->
      <div class="band-wrapper">
        <div class="band band-conservative" :style="{ flex: bandWeight('conservative') }">
          <span class="band-label">保守型</span>
        </div>
        <div class="band band-balanced" :style="{ flex: bandWeight('balanced') }">
          <span class="band-label">平衡型</span>
        </div>
        <div class="band band-aggressive" :style="{ flex: bandWeight('aggressive') }">
          <span class="band-label">激进型</span>
        </div>
        <div class="marker" :style="{ left: markerPct + '%' }">
          <div class="marker-dot"></div>
          <div class="marker-num">{{ profile.score }}</div>
        </div>
      </div>

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
              {{ opt.label }} <span class="opt-score">({{ opt.value }} 分)</span>
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
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useInvestmentStore } from '@/stores/investment'
import { useUserStore } from '@/stores/user'

const store = useInvestmentStore()
const userStore = useUserStore()

const questions = ref([])
const answers = reactive({})
const profile = ref(null)
const thresholds = ref({
  conservative: [5, 10],
  balanced: [11, 18],
  aggressive: [19, 25],
})
const maxScore = ref(25)
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

function bandWeight(level) {
  const [lo, hi] = thresholds.value[level] || [0, 0]
  return Math.max(1, hi - lo + 1)
}

const markerPct = computed(() => {
  if (!profile.value) return 0
  const min = thresholds.value.conservative?.[0] ?? 5
  const max = thresholds.value.aggressive?.[1] ?? maxScore.value
  const span = Math.max(1, max - min)
  const pct = ((profile.value.score - min) / span) * 100
  return Math.max(0, Math.min(100, pct))
})

async function load() {
  loading.value = true
  try {
    const data = await store.fetchRiskQuiz()
    questions.value = data.questions || []
    profile.value = data.profile || null
    if (data.thresholds) thresholds.value = data.thresholds
    if (data.max_score) maxScore.value = data.max_score
    editing.value = !profile.value
  } finally {
    loading.value = false
  }
}

async function submit() {
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
    if (result?.thresholds) thresholds.value = result.thresholds
    if (result?.max_score) maxScore.value = result.max_score
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
.rule-alert { margin-bottom: 14px; }
.threshold-pill {
  display: inline-block; margin: 2px 8px 0 0;
  font-size: 12px; color: var(--color-text-muted);
}

.profile { display: flex; flex-direction: column; gap: 14px; }

.score-display {
  display: flex; justify-content: space-between; align-items: baseline;
  flex-wrap: wrap; gap: 12px;
}
.score-num strong {
  font-size: 34px; color: var(--color-primary); font-weight: 700;
}
.score-denom { font-size: 15px; color: var(--color-text-muted); margin-left: 4px; }
.score-level { font-size: 14px; }
.score-level strong { margin-left: 6px; font-size: 16px; }
/* 文字色用深色调以满足 WCAG AA 对比度（band 背景色保留鲜艳） */
.level-conservative { color: #15803D; }
.level-balanced { color: #B45309; }
.level-aggressive { color: #DC2626; }

.band-wrapper {
  position: relative;
  display: flex; height: 22px; border-radius: 11px;
  overflow: visible;
}
.band {
  position: relative;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; color: white; font-weight: 600;
}
.band-conservative { background: #22C55E; border-radius: 11px 0 0 11px; }
.band-balanced     { background: #F59E0B; }
.band-aggressive   { background: #EF4444; border-radius: 0 11px 11px 0; }
.marker {
  position: absolute; top: -6px; transform: translateX(-50%);
  display: flex; flex-direction: column; align-items: center;
  pointer-events: none;
}
.marker-dot {
  width: 10px; height: 34px; background: var(--color-text);
  border-radius: 3px; border: 2px solid white;
  box-shadow: 0 2px 6px rgba(0,0,0,0.25);
}
.marker-num {
  margin-top: 2px; font-size: 11px; font-weight: 700;
  color: var(--color-text); background: var(--color-surface);
  padding: 1px 5px; border-radius: 4px;
  border: 1px solid var(--color-border);
}

.summary {
  font-size: 13px;
  color: var(--color-text-muted);
  padding: 10px 12px;
  background: #F0F7FF;
  border-radius: 8px;
  line-height: 1.6;
}
.empty { text-align: center; color: var(--color-text-muted); padding: 24px 0; }
.form-footer { display: flex; justify-content: flex-end; gap: 8px; }
.el-radio-group {
  display: flex; flex-direction: column; align-items: flex-start; gap: 6px;
}
.opt-score { color: var(--color-text-muted); font-size: 12px; margin-left: 2px; }
</style>
