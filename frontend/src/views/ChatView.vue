<template>
  <div class="chat-page">
    <div class="chat-container" ref="chatRef">
      <!-- 欢迎头部 -->
      <div class="chat-header-hint">
        <span>💬 智能记账助手Anon</span>
      </div>

      <div v-for="(msg, i) in messages" :key="i" :class="['msg', msg.sender]">
        <img v-if="msg.sender === 'assistant'" src="/favicon.ico" class="avatar ai-avatar" alt="Anon" />
        <div class="msg-body">
          <img v-if="msg.image" :src="msg.image" class="chat-image" alt="uploaded" />
          <div v-if="msg.content" class="bubble">{{ msg.content }}</div>

          <!-- 可编辑确认卡片 -->
          <template v-if="msg.pending_records && msg.pending_records.length">
            <div
              v-for="(rec, ri) in msg.pending_records"
              :key="ri"
              v-show="rec._state !== 'cancelled'"
              :class="['pending-card', rec.type === 'expense' ? 'card-expense' : 'card-income', rec._state === 'confirmed' ? 'card-confirmed' : '']"
            >
              <!-- 已确认：只读展示 -->
              <template v-if="rec._state === 'confirmed'">
                <div class="card-confirmed-header">
                  <span :class="rec.type === 'expense' ? 'amount-expense' : 'amount-income'">
                    {{ rec.type === 'expense' ? '-' : '+' }}¥{{ rec._edit.amount }}
                  </span>
                  <span class="card-category-text">{{ rec._edit.category }}</span>
                  <span class="card-confirmed-badge">✓ 已记录</span>
                </div>
                <div class="card-rows">
                  <div class="card-row">
                    <span class="card-label">日期</span>
                    <span class="card-value">{{ rec._edit.date }}</span>
                  </div>
                  <div class="card-row">
                    <span class="card-label">备注</span>
                    <span class="card-value">{{ rec._edit.note || '—' }}</span>
                  </div>
                </div>
              </template>

              <!-- 待确认：可编辑 -->
              <template v-else>
                <div class="card-fields">
                  <div class="card-field">
                    <label class="field-label">分类</label>
                    <el-input v-model="rec._edit.category" size="small" placeholder="分类" />
                  </div>
                  <div class="card-field">
                    <label class="field-label">金额</label>
                    <el-input-number
                      v-model="rec._edit.amount"
                      :min="0"
                      size="small"
                      style="width:100%"
                      controls-position="right"
                    />
                  </div>
                  <div class="card-field">
                    <label class="field-label">日期</label>
                    <el-date-picker
                      v-model="rec._edit.date"
                      type="date"
                      value-format="YYYY-MM-DD"
                      size="small"
                      style="width:100%"
                    />
                  </div>
                  <div class="card-field">
                    <label class="field-label">备注</label>
                    <el-input v-model="rec._edit.note" size="small" placeholder="备注（可选）" />
                  </div>
                </div>
                <div class="card-actions">
                  <el-button size="small" plain @click="rec._state = 'cancelled'">取消</el-button>
                  <el-button size="small" type="primary" @click="confirmRecord(rec)">✓ 确认记录</el-button>
                </div>
              </template>
            </div>
          </template>
        </div>
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
      <input
        ref="imageInput"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        style="display:none"
        @change="handleImageSelect"
      />
      <button class="img-btn" :disabled="loading" @click="$refs.imageInput.click()" title="上传图片识别记账">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/>
        </svg>
      </button>
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
import { ref, computed, onMounted, onActivated, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useCategoryStore } from '@/stores/categories'

const userStore = useUserStore()
const categoryStore = useCategoryStore()

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
const imageInput = ref(null)
const messages = ref([{ sender: 'assistant', content: '你好！我是你的智能记账助手 😊 你可以告诉我消费情况，例如"吃饭花了20元"，也可以点击图片按钮上传账单/小票自动识别记账。' }])
const loading = ref(false)
const chatRef = ref(null)
const router = useRouter()
const currentUser = computed(() => userStore.username)

async function sendMessage() {
  const msg = userInput.value.trim()
  if (!msg) return
  messages.value.push({ sender: 'user', content: msg })
  userInput.value = ''
  loading.value = true
  await scrollToBottom()

  try {
    const llm = userStore.llmPayload
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ message: msg, llm })
    })
    const data = await res.json()
    const assistantMsg = { sender: 'assistant', content: data.reply || '⚠️ 无法解析' }
    if (data.pending_records && data.pending_records.length > 0) {
      assistantMsg.pending_records = data.pending_records.map(rec => ({
        ...rec,
        _state: 'pending',
        _edit: { ...rec }
      }))
    }
    messages.value.push(assistantMsg)
  } catch {
    messages.value.push({ sender: 'assistant', content: '❌ 网络异常，请检查后端是否启动！' })
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

function handleImageSelect(e) {
  const file = e.target.files[0]
  if (!file) return
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.error('图片大小不能超过 10MB')
    e.target.value = ''
    return
  }
  sendImage(file)
  e.target.value = ''
}

async function sendImage(file) {
  const previewUrl = URL.createObjectURL(file)
  messages.value.push({ sender: 'user', content: '', image: previewUrl })
  loading.value = true
  await scrollToBottom()

  try {
    const formData = new FormData()
    formData.append('image', file)
    const res = await fetch('/api/chat/image', {
      method: 'POST',
      credentials: 'include',
      body: formData
    })
    const data = await res.json()
    const assistantMsg = { sender: 'assistant', content: data.reply || '⚠️ 无法解析' }
    if (data.pending_records && data.pending_records.length > 0) {
      assistantMsg.pending_records = data.pending_records.map(rec => ({
        ...rec,
        _state: 'pending',
        _edit: { ...rec }
      }))
    }
    messages.value.push(assistantMsg)
  } catch {
    messages.value.push({ sender: 'assistant', content: '❌ 图片识别失败，请重试或手动输入。' })
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

async function confirmRecord(rec) {
  try {
    const res = await fetch('/api/commit_record', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        type: rec.type,
        category: rec._edit.category,
        amount: rec._edit.amount,
        date: rec._edit.date,
        note: rec._edit.note,
      })
    })
    const data = await res.json()
    if (data.success) {
      rec._state = 'confirmed'
      categoryStore.bumpRefresh()
    } else {
      ElMessage.error(data.message || '记录失败')
    }
  } catch {
    ElMessage.error('网络异常')
  }
}

function scrollToBottom() {
  return nextTick(() => {
    if (chatRef.value) chatRef.value.scrollTop = chatRef.value.scrollHeight
  })
}

let lastUser = userStore.username
onMounted(() => {
  if (!userStore.username) router.push('/login')
  else scrollToBottom()
})

onActivated(() => {
  if (userStore.username !== lastUser) {
    lastUser = userStore.username
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

/* msg-body: 纵向堆叠 bubble + 卡片 */
.msg-body {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  max-width: 72%;
  gap: 6px;
}
.msg.user .msg-body { align-items: flex-end; }

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
  width: fit-content;
  max-width: 100%;
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

/* 确认卡片 */
.pending-card {
  background: var(--color-surface);
  border-radius: 12px;
  padding: 12px 14px;
  border: 1px solid var(--color-border);
  width: 100%;
  box-sizing: border-box;
  font-size: 13px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}
.card-expense { border-left: 3px solid #ef4444; }
.card-income  { border-left: 3px solid #22c55e; }
.card-confirmed { background: var(--color-bg); opacity: 0.85; }

/* 已确认只读头部 */
.card-confirmed-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.card-category-text { font-weight: 600; color: var(--color-text); flex: 1; }
.card-confirmed-badge { font-size: 11px; color: #22c55e; font-weight: 600; flex-shrink: 0; }
.amount-expense { color: #ef4444; font-weight: 700; font-size: 15px; }
.amount-income  { color: #22c55e; font-weight: 700; font-size: 15px; }

/* 编辑字段区：PC 2列 */
.card-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 12px;
  margin-bottom: 10px;
}
.card-field { display: flex; flex-direction: column; gap: 3px; }
.field-label { font-size: 11px; color: var(--color-text-muted); font-weight: 500; }

/* 操作按钮 */
.card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* 已确认只读字段行 */
.card-rows { display: flex; flex-direction: column; }
.card-row {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  border-top: 1px solid var(--color-border);
  font-size: 12px;
}
.card-label { color: var(--color-text-muted); }
.card-value { color: var(--color-text); text-align: right; }

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

/* 图片消息 */
.chat-image {
  max-width: 200px;
  max-height: 200px;
  border-radius: 12px;
  object-fit: cover;
  cursor: pointer;
  border: 1px solid var(--color-border);
}

/* 输入区 */
.chat-input {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px 12px;
  margin: 0 12px 12px;
  background: var(--color-surface);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}
.img-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.img-btn:hover:not(:disabled) {
  background: var(--color-primary-light);
  border-color: var(--color-primary);
  color: var(--color-primary);
}
.img-btn:disabled { opacity: 0.5; cursor: not-allowed; }
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
  .msg-body { max-width: 85%; }
  .card-fields { grid-template-columns: 1fr; }
  .card-actions { gap: 6px; }
  .card-actions .el-button { flex: 1; }
}
</style>
