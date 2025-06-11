<template>
  <div class="chat-page">
    <!-- 聊天记录区域 -->
    <div class="chat-container" ref="chatRef">
      <div v-for="(msg, i) in messages" :key="i" :class="['msg', msg.sender]">
        <div class="bubble">{{ msg.content }}</div>
      </div>
    </div>

    <!-- 输入区域，固定底部 -->
    <div class="chat-input">
      <el-input
        v-model="userInput"
        placeholder="请输入消费记录，如 吃饭花了20"
        @keyup.enter="sendMessage"
        size="large"
      />
      <el-button type="primary" @click="sendMessage" :disabled="loading" size="large">
        {{ loading ? '发送中...' : '发送' }}
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated, nextTick } from 'vue'
import { useRouter } from 'vue-router'

const userInput = ref('')
const messages = ref([{ sender: 'assistant', content: '你好，我是你的智能记账助手，有什么可以帮你？' }])
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
    const res = await fetch('/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify({ message: msg, llm })
    })
    const data = await res.json()
    messages.value.push({ sender: 'assistant', content: data.reply || '⚠️ 无法解析' })
    if (data.reply?.startsWith('✅')) {
      localStorage.setItem('record_added', Date.now())
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
  if (!name) {
    router.push('/login')
  } else {
    scrollToBottom()
  }
})

onActivated(() => {
  const name = localStorage.getItem('username') || ''
  if (name !== currentUser.value) {
    currentUser.value = name
    messages.value = [
      { sender: 'assistant', content: '你好，我是你的智能记账助手，有什么可以帮你？' }
    ]
  }
})
</script>

<style scoped>
.chat-page {
  position: relative;
  height: 100vh;
  height: 100dvh;
  display: flex;
  flex-direction: column;
}

.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
  padding-bottom: 70px;
  background-color: #f9f9f9;
}

.msg {
  display: flex;
  margin: 6px 0;
}
.msg.user {
  justify-content: flex-end;
}
.msg.assistant {
  justify-content: flex-start;
}
.bubble {
  padding: 8px 12px;
  border-radius: 6px;
  max-width: 75%;
  word-break: break-word;
}
.user .bubble {
  background-color: #c6e2ff;
}
.assistant .bubble {
  background-color: #eef1f6;
}

.chat-input {
  display: flex;
  padding: 10px;
  border-top: 1px solid #ddd;
  background: #fff;
  position: stricky;
  z-index: 100;
}
.chat-input .el-input {
  flex: 1;
}
.chat-input .el-button {
  margin-left: 10px;
}
</style>





