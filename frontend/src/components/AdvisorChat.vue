<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <span>💬 AI 投资顾问</span>
        <div class="actions">
          <el-button size="small" :loading="loading" @click="analyzePortfolio">一键诊断持仓</el-button>
          <el-button size="small" text type="danger" @click="clear">清空对话</el-button>
        </div>
      </div>
    </template>

    <div class="disclaimer">
      ⚠️ AI 给出的内容仅供参考，不构成具体投资建议，请结合自身情况谨慎决策。
    </div>

    <div ref="scrollRef" class="messages">
      <div v-if="!messages.length" class="empty">
        你可以问我："我的持仓风险高吗？""有什么再平衡建议？""怎么达成我的理财目标？"
        <br /><br />
        💡 也可以上传持仓截图或目标截图，Anon 会自动识别并生成待确认的入库卡。
      </div>
      <div
        v-for="(m, i) in messages"
        :key="i"
        :class="['msg-wrapper', m.role]"
      >
        <div class="bubble" :class="m.role">
          <div class="bubble-role">{{ m.role === 'user' ? '你' : 'Anon' }}</div>
          <img v-if="m.image" :src="m.image" class="msg-image" />
          <div v-if="m.content" class="bubble-content" v-html="render(m.content)"></div>
        </div>
        <template v-if="m.pending_assets && m.pending_assets.length">
          <PendingAssetCard
            v-for="(rec, ai) in m.pending_assets"
            :key="`a${i}-${ai}`"
            :rec="rec"
            @cancel="rec._state = 'cancelled'"
            @confirm="confirmAsset(rec)"
          />
        </template>
        <template v-if="m.pending_goals && m.pending_goals.length">
          <PendingGoalCard
            v-for="(rec, gi) in m.pending_goals"
            :key="`g${i}-${gi}`"
            :rec="rec"
            @cancel="rec._state = 'cancelled'"
            @confirm="confirmGoal(rec)"
          />
        </template>
      </div>
      <div v-if="loading" class="bubble assistant">
        <div class="bubble-role">Anon</div>
        <div class="bubble-content typing">正在思考…</div>
      </div>
    </div>

    <div class="composer">
      <input
        ref="imageInput"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        style="display:none"
        @change="handleImageSelect"
      />
      <el-button
        class="img-upload-btn"
        :disabled="loading"
        :title="'上传持仓 / 目标截图识别'"
        @click="imageInput?.click()"
      >📷</el-button>
      <el-input
        v-model="draft"
        type="textarea"
        :rows="2"
        :disabled="loading"
        placeholder="问问 Anon 关于你的投资组合或目标（Enter 发送，Shift+Enter 换行）"
        @keydown.enter.exact.prevent="send"
      />
      <el-button type="primary" :loading="loading" @click="send">发送</el-button>
    </div>
  </el-card>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { useInvestmentStore } from '@/stores/investment'
import { useUserStore } from '@/stores/user'
import PendingAssetCard from '@/components/PendingAssetCard.vue'
import PendingGoalCard from '@/components/PendingGoalCard.vue'

const store = useInvestmentStore()
const userStore = useUserStore()

const messages = ref([])
const draft = ref('')
const loading = ref(false)
const scrollRef = ref(null)
const imageInput = ref(null)

function scrollToBottom() {
  nextTick(() => {
    if (scrollRef.value) scrollRef.value.scrollTop = scrollRef.value.scrollHeight
  })
}

async function send() {
  const text = draft.value.trim()
  if (!text || loading.value) return
  messages.value.push({ role: 'user', content: text })
  draft.value = ''
  loading.value = true
  scrollToBottom()
  try {
    const res = await store.askAdvisor({
      mode: 'general',
      history: messages.value.map(m => ({ role: m.role, content: m.content })),
      llm: userStore.llmPayload,
    })
    messages.value.push({ role: 'assistant', content: res.reply || '（空回复）' })
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '对话失败，请稍后重试')
    messages.value.push({ role: 'assistant', content: '⚠️ 暂时无法获取回复，请稍后再试。' })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

async function analyzePortfolio() {
  if (loading.value) return
  loading.value = true
  messages.value.push({ role: 'user', content: '帮我分析当前投资组合' })
  scrollToBottom()
  try {
    const res = await store.askAdvisor({ mode: 'portfolio', llm: userStore.llmPayload })
    messages.value.push({ role: 'assistant', content: res.reply || '（空回复）' })
  } catch (e) {
    ElMessage.error(e.response?.data?.message || 'AI 诊断失败')
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

function clear() {
  messages.value = []
}

function handleImageSelect(e) {
  const file = e.target.files[0]
  if (!file) return
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.error('图片大小不能超过 10MB')
    e.target.value = ''
    return
  }
  uploadImage(file)
  e.target.value = ''
}

async function uploadImage(file) {
  const previewUrl = URL.createObjectURL(file)
  messages.value.push({ role: 'user', content: '（上传了一张图片）', image: previewUrl })
  loading.value = true
  scrollToBottom()
  try {
    const fd = new FormData()
    fd.append('image', file)
    const res = await fetch('/api/investment/parse-image', {
      method: 'POST',
      credentials: 'include',
      body: fd,
    })
    const data = await res.json()
    if (!res.ok) {
      messages.value.push({ role: 'assistant', content: data.error || '识别失败' })
      return
    }
    const msg = { role: 'assistant', content: data.reply || '已识别' }
    if (data.pending_assets?.length) {
      msg.pending_assets = data.pending_assets.map(a => ({ ...a, _state: 'pending', _edit: { ...a } }))
    }
    if (data.pending_goals?.length) {
      msg.pending_goals = data.pending_goals.map(g => ({ ...g, _state: 'pending', _edit: { ...g } }))
    }
    messages.value.push(msg)
  } catch {
    messages.value.push({ role: 'assistant', content: '❌ 网络异常，请稍后重试。' })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

async function confirmAsset(rec) {
  rec._state = 'saving'
  rec._error = ''
  try {
    const res = await store.commitPendingAsset({ ...rec._edit })
    if (res?.success) {
      rec._state = 'confirmed'
      ElMessage.success('已添加到投资理财')
    } else {
      rec._state = 'error'
      rec._error = res?.message || '入库失败'
    }
  } catch (e) {
    rec._state = 'error'
    rec._error = e?.response?.data?.message || e?.response?.data?.error || '网络异常'
  }
}

async function confirmGoal(rec) {
  rec._state = 'saving'
  rec._error = ''
  try {
    const res = await store.commitPendingGoal({ ...rec._edit })
    if (res?.success) {
      rec._state = 'confirmed'
      ElMessage.success('已添加理财目标')
    } else {
      rec._state = 'error'
      rec._error = res?.message || '入库失败'
    }
  } catch (e) {
    rec._state = 'error'
    rec._error = e?.response?.data?.message || e?.response?.data?.error || '网络异常'
  }
}

function render(md) {
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc(md)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
    .replace(/\n/g, '<br/>')
}
</script>

<style scoped>
.header-row {
  display: flex; justify-content: space-between; align-items: center; width: 100%;
}
.actions { display: flex; gap: 6px; }
.disclaimer {
  margin-bottom: 10px;
  padding: 8px 12px;
  background: #FFF7ED;
  color: #9A3412;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.6;
}
.messages {
  height: 360px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 6px 2px;
}
.empty {
  color: var(--color-text-muted);
  text-align: center;
  margin: auto 0;
  font-size: 13px;
}
.bubble {
  max-width: 86%;
  padding: 10px 12px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}
.bubble.user {
  align-self: flex-end;
  background: var(--color-primary);
  color: #fff;
}
.bubble.assistant {
  align-self: flex-start;
  background: var(--color-primary-light);
  color: var(--color-text);
  border: 1px solid var(--color-border);
}
.bubble-role {
  font-size: 11px;
  opacity: 0.7;
  margin-bottom: 4px;
}
.typing { font-style: italic; opacity: 0.8; }

.msg-wrapper {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-width: 86%;
}
.msg-wrapper.user { align-self: flex-end; align-items: flex-end; }
.msg-wrapper.assistant { align-self: flex-start; align-items: flex-start; }
.msg-image {
  max-width: 160px;
  max-height: 160px;
  border-radius: 8px;
  margin-top: 4px;
  display: block;
}

.composer {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  align-items: flex-end;
}
.composer .el-textarea { flex: 1; }
.img-upload-btn {
  flex-shrink: 0;
  padding: 0;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  font-size: 16px;
}
</style>
