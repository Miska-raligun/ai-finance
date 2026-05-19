<template>
  <el-dialog
    v-model="visible"
    title="💭 买之前问一下"
    :width="dialogWidth"
    append-to-body
    @open="onOpen"
  >
    <div class="dh-form">
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="想买什么">
          <el-input
            v-model="form.item"
            placeholder="例：机械键盘 / 健身年卡 / 出去吃顿好的"
            maxlength="80"
            show-word-limit
            clearable
          />
        </el-form-item>
        <el-form-item label="价格 (¥)">
          <el-input-number
            v-model="form.price"
            :min="0"
            :max="1000000"
            :step="50"
            :precision="2"
            controls-position="right"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="分类（可选）">
          <el-input
            v-model="form.category"
            placeholder="数码 / 餐饮 / 教育…"
            maxlength="30"
            clearable
          />
        </el-form-item>
        <el-form-item label="补充说明（可选）">
          <el-input
            v-model="form.note"
            type="textarea"
            :rows="2"
            placeholder="为什么想买？打算多久用？"
            maxlength="200"
            show-word-limit
          />
        </el-form-item>
      </el-form>

      <div class="dh-actions">
        <el-button
          type="primary"
          :loading="loading"
          :disabled="!canSubmit"
          @click="submit"
        >
          {{ loading ? '正在分析…' : '让 Anon 给我个建议' }}
        </el-button>
      </div>

      <div v-if="result" class="dh-result" :class="verdictClass">
        <div class="dh-verdict">
          <span class="dh-verdict-emoji">{{ verdictEmoji }}</span>
          <span class="dh-verdict-text">{{ result.verdict }}</span>
          <span v-if="result.source === 'fallback'" class="dh-source-tag">本地规则</span>
        </div>

        <div class="dh-reason" v-html="formattedReason"></div>

        <div v-if="result.impact" class="dh-impact">
          <div class="impact-row">
            <span class="impact-label">价格</span>
            <strong>¥{{ result.impact.price.toFixed(2) }}</strong>
          </div>
          <div v-if="result.impact.as_pct_of_avg_monthly_spend != null" class="impact-row">
            <span class="impact-label">占月均支出</span>
            <strong :class="pctClass(result.impact.as_pct_of_avg_monthly_spend)">
              {{ result.impact.as_pct_of_avg_monthly_spend }}%
            </strong>
          </div>
          <div v-if="result.impact.as_pct_of_net_30d != null" class="impact-row">
            <span class="impact-label">占近 30 天净流入</span>
            <strong :class="pctClass(result.impact.as_pct_of_net_30d)">
              {{ result.impact.as_pct_of_net_30d }}%
            </strong>
          </div>
          <div v-if="result.impact.budget_left_after != null" class="impact-row">
            <span class="impact-label">买后本月预算余</span>
            <strong :class="result.impact.budget_left_after < 0 ? 'over-budget' : ''">
              ¥{{ result.impact.budget_left_after.toFixed(0) }}
            </strong>
          </div>
        </div>

        <div v-if="result.alternatives && result.alternatives.length" class="dh-section">
          <div class="dh-section-title">💡 更便宜的替代</div>
          <ul class="dh-list">
            <li v-for="(a, i) in result.alternatives" :key="'a' + i">{{ a }}</li>
          </ul>
        </div>

        <div v-if="result.tips && result.tips.length" class="dh-section">
          <div class="dh-section-title">🧠 购买技巧</div>
          <ul class="dh-list">
            <li v-for="(t, i) in result.tips" :key="'t' + i">{{ t }}</li>
          </ul>
        </div>

        <div class="dh-foot-hint">
          数据来自你近 3 个月的实际记账，仅供参考 · 最终决定还是你说了算
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const _mq = window.matchMedia('(max-width: 768px)')
const isMobile = ref(_mq.matches)
function _onMq(e) { isMobile.value = e.matches }
onMounted(() => _mq.addEventListener('change', _onMq))
onBeforeUnmount(() => _mq.removeEventListener('change', _onMq))
const dialogWidth = computed(() => isMobile.value ? 'calc(100vw - 28px)' : '520px')

const form = ref({ item: '', price: null, category: '', note: '' })
const loading = ref(false)
const result = ref(null)

const canSubmit = computed(() =>
  !!form.value.item.trim() && form.value.price > 0 && !loading.value
)

function onOpen() {
  // 不重置表单，让用户调价后能重新分析；只清旧结果
  result.value = null
}

async function submit() {
  if (!canSubmit.value) return
  loading.value = true
  try {
    const res = await api.post('/api/decide', {
      item: form.value.item.trim(),
      price: Number(form.value.price),
      category: form.value.category.trim() || undefined,
      note: form.value.note.trim() || undefined,
      // 用户在前端选了「自定义 LLM」时把 key 直接传过去；'default' 模式下为 null
      llm: userStore.llmPayload,
    })
    result.value = res.data
  } catch (e) {
    const msg = e?.response?.data?.error || '分析失败，稍后再试'
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}

const verdictEmoji = computed(() => {
  const v = result.value?.verdict || ''
  if (v.includes('放弃')) return '🛑'
  if (v.includes('等等') || v.includes('谨慎')) return '🤔'
  if (v.includes('更便宜')) return '💡'
  if (v.includes('买')) return '✅'
  return '🤔'
})
const verdictClass = computed(() => {
  const v = result.value?.verdict || ''
  if (v.includes('放弃')) return 'verdict-no'
  if (v.includes('等等') || v.includes('谨慎')) return 'verdict-wait'
  if (v.includes('买')) return 'verdict-yes'
  return ''
})

function pctClass(pct) {
  if (pct == null) return ''
  if (pct >= 50) return 'pct-high'
  if (pct >= 20) return 'pct-mid'
  return ''
}

const formattedReason = computed(() => {
  const r = result.value?.reason || ''
  // 简单转义后把换行变 <br>
  const esc = r.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc.replace(/\n/g, '<br>')
})
</script>

<style scoped>
.dh-form { display: flex; flex-direction: column; gap: 4px; }
.dh-actions {
  display: flex;
  justify-content: center;
  margin: 6px 0 4px;
}

.dh-result {
  margin-top: 16px;
  padding: 16px;
  border-radius: 16px;
  background: var(--color-surface-2);
  border: 2px dashed var(--color-border);
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.dh-result.verdict-yes  { border-color: #6fba2c; background: #f4faec; }
.dh-result.verdict-wait { border-color: #f5c31c; background: #fef8e1; }
.dh-result.verdict-no   { border-color: #e05a5a; background: #fdecec; }

.dh-verdict {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 18px;
  font-weight: 900;
  color: var(--color-text);
}
.dh-verdict-emoji { font-size: 24px; }
.dh-source-tag {
  margin-left: auto;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 50px;
  background: var(--color-border);
  color: var(--color-text-muted);
}

.dh-reason {
  font-size: 13px;
  line-height: 1.65;
  color: var(--color-text);
}

.dh-impact {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}
.impact-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--color-surface);
  border-radius: 10px;
  font-size: 12px;
}
.impact-label { color: var(--color-text-muted); }
.impact-row strong {
  font-variant-numeric: tabular-nums;
  font-weight: 800;
  color: var(--color-text-strong);
}
.pct-mid { color: #d97706; }
.pct-high { color: #c0392b; }
.over-budget { color: #c0392b; }

.dh-section-title {
  font-weight: 800;
  font-size: 13px;
  margin-bottom: 6px;
  color: var(--color-text-strong);
}
.dh-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: var(--color-text);
}
.dh-list li {
  padding: 6px 12px;
  background: var(--color-surface);
  border-radius: 10px;
  border-left: 3px solid var(--color-primary);
}

.dh-foot-hint {
  font-size: 11px;
  color: var(--color-text-muted);
  text-align: center;
  padding-top: 4px;
}

@media (max-width: 480px) {
  .dh-impact { grid-template-columns: 1fr; }
  .dh-verdict { font-size: 16px; }
  .dh-verdict-emoji { font-size: 20px; }
}
</style>
