<template>
  <div class="chat-page">
    <div class="chat-container" ref="chatRef">
      <!-- 欢迎头部 -->
      <div class="chat-header-hint">
        <span>💬 智能记账助手Anon</span>
      </div>

      <div v-for="(msg, i) in messages" :key="i" :class="['msg', msg.sender]">
        <img v-if="msg.sender === 'assistant'" src="/favicon.ico" class="avatar ai-avatar" alt="Anon" />
        <div class="bubble">{{ msg.content }}</div>
        <div v-if="msg.sender === 'user'" class="avatar user-avatar">
          {{ currentUser.slice(0, 1).toUpperCase() }}
        </div>
      </div>

      <div v-if="loading" class="msg assistant">
        <img src="/favicon.ico" class="avatar ai-avatar" alt="Anon" />
        <div class="bubble typing">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>

    <div class="quick-actions">
      <button
        v-for="q in quickActions"
        :key="q.label"
        class="quick-btn"
        :disabled="loading"
        @click="sendQuick(q.text)"
      >{{ q.label }}</button>
    </div>

    <div class="chat-input">
      <el-input
        v-model="userInput"
        placeholder="告诉我你的消费，如：吃饭花了20元"
        @keyup.enter="sendMessage"
        size="large"
        class="chat-text-input"
      />
      <el-button
        type="primary"
        @click="sendMessage"
        :disabled="loading"
        size="large"
        class="send-btn"
      >
        发送
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated, nextTick } from 'vue'
import { useRouter } from 'vue-router'

const quickActions = [
  { label: '📊 分析本月财务', text: '分析一下我本月的财务状况' },
  { label: '💡 智能推荐预算', text: '根据我的消费习惯帮我推荐合适的预算' },
  { label: '💰 查看预算余额', text: '查询本月各分类预算余额' },
]
function sendQuick(text) {
  userInput.value = text
  sendMessage()
}

const userInput = ref('')
const messages = ref([{ sender: 'assistant', content: '你好！我是你的智能记账助手 😊 你可以告诉我消费情况，例如"吃饭花了20元"，我会帮你自动记录。' }])
const loading = ref(false)
const chatRef = ref(null)
const router = useRouter()
const currentUser = ref(localStorage.getItem('username') || '')

async function sendMessage() {
  const msg = userInput.value.trim()
  if (!msg) return
  messages.value.push({ sender: 'user', content: msg })
  userInput.value = ''
  loading.value = true
  await scrollToBottom()

  try {
    const cfgRaw = localStorage.getItem('llmConfig')
    let llm = null
    if (cfgRaw && cfgRaw !== 'default') {
      try { llm = JSON.parse(cfgRaw) } catch {}
    }
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ message: msg, llm })
    })
    const data = await res.json()
    messages.value.push({ sender: 'assistant', content: data.reply || '⚠️ 无法解析' })
    if (data.reply?.startsWith('✅')) {
      window.dispatchEvent(new CustomEvent('record_changed'))
    }
  } catch {
    messages.value.push({ sender: 'assistant', content: '❌ 网络异常，请检查后端是否启动！' })
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

function scrollToBottom() {
  return nextTick(() => {
    if (chatRef.value) chatRef.value.scrollTop = chatRef.value.scrollHeight
  })
}

onMounted(() => {
  const name = localStorage.getItem('username')
  if (!name) router.push('/login')
  else scrollToBottom()
})

onActivated(() => {
  const name = localStorage.getItem('username') || ''
  if (name !== currentUser.value) {
    currentUser.value = name
    messages.value = [{ sender: 'assistant', content: '你好！我是你的智能记账助手 😊 你可以告诉我消费情况，例如"吃饭花了20元"，我会帮你自动记录。' }]
  }
})
</script>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 40px);
  height: calc(100dvh - 40px);
  background: #EFF6FF;
}

.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-header-hint {
  text-align: center;
  font-size: 12px;
  color: var(--color-text-muted);
  padding: 4px 12px;
  background: rgba(37,99,235,0.08);
  border-radius: 20px;
  align-self: center;
  margin-bottom: 4px;
}

.msg {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}
.msg.user { justify-content: flex-end; }
.msg.assistant { justify-content: flex-start; }

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.ai-avatar {
  object-fit: cover;
  background: transparent;
  border-radius: 50%;
  border: 1px solid var(--color-border);
}
.user-avatar {
  background: var(--color-primary);
  color: #fff;
}

.bubble {
  padding: 10px 14px;
  border-radius: 16px;
  max-width: 72%;
  word-break: break-word;
  font-size: 14px;
  line-height: 1.6;
}
.user .bubble {
  background: var(--color-primary);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.assistant .bubble {
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-bottom-left-radius: 4px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}

/* 打字动画气泡 */
.typing {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 12px 16px;
}
.typing span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-text-muted);
  animation: blink 1.2s infinite;
}
.typing span:nth-child(2) { animation-delay: 0.2s; }
.typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink {
  0%, 80%, 100% { opacity: 0.25; transform: scale(0.85); }
  40% { opacity: 1; transform: scale(1); }
}

/* 快捷操作 */
.quick-actions {
  display: flex;
  gap: 8px;
  padding: 0 12px 8px;
  overflow-x: auto;
  scrollbar-width: none;
}
.quick-actions::-webkit-scrollbar { display: none; }
.quick-btn {
  flex-shrink: 0;
  padding: 5px 12px;
  border-radius: 16px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.quick-btn:hover:not(:disabled) {
  background: var(--color-primary-light);
  border-color: var(--color-primary);
  color: var(--color-primary);
}
.quick-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* 输入区 */
.chat-input {
  display: flex;
  gap: 10px;
  padding: 10px 12px 12px;
  margin: 0 12px 12px;
  background: var(--color-surface);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}
.chat-text-input { flex: 1; }
.send-btn {
  flex-shrink: 0;
  min-width: 72px;
  font-weight: 600;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .chat-page {
    height: calc(100dvh - var(--topbar-height) - 0px);
  }
  .bubble { max-width: 82%; }
}
</style>
