<template>
  <el-tooltip
    :content="supported ? (recording ? '点击停止' : '语音输入') : '当前浏览器不支持语音识别'"
    placement="top"
  >
    <button
      class="voice-btn"
      :class="{ recording, disabled: !supported }"
      :disabled="!supported || disabled"
      @click="toggle"
    >
      <span v-if="recording" class="dot"></span>
      <span class="icon">🎙️</span>
    </button>
  </el-tooltip>
</template>

<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  lang: { type: String, default: 'zh-CN' },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['result', 'partial'])

const SR = window.SpeechRecognition || window.webkitSpeechRecognition
const supported = !!SR
const recording = ref(false)

let rec = null

function start() {
  if (!supported || recording.value) return
  rec = new SR()
  rec.lang = props.lang
  rec.interimResults = true
  rec.continuous = false
  let finalText = ''

  rec.onresult = (e) => {
    let interim = ''
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const t = e.results[i][0].transcript
      if (e.results[i].isFinal) finalText += t
      else interim += t
    }
    emit('partial', finalText + interim)
  }
  rec.onerror = (e) => {
    if (e.error === 'no-speech') {
      ElMessage.warning('未检测到语音')
    } else if (e.error === 'not-allowed') {
      ElMessage.error('请允许浏览器使用麦克风')
    } else if (e.error !== 'aborted') {
      ElMessage.error(`语音识别失败：${e.error}`)
    }
    cleanup()
  }
  rec.onend = () => {
    if (finalText.trim()) emit('result', finalText.trim())
    cleanup()
  }

  try {
    rec.start()
    recording.value = true
  } catch (e) {
    ElMessage.error('启动语音识别失败')
    cleanup()
  }
}

function stop() {
  if (rec && recording.value) {
    try { rec.stop() } catch {}
  }
}

function cleanup() {
  recording.value = false
  rec = null
}

function toggle() {
  if (!supported) {
    ElMessage.warning('当前浏览器不支持语音识别（请使用 Chrome / Edge）')
    return
  }
  recording.value ? stop() : start()
}

onBeforeUnmount(stop)
</script>

<style scoped>
.voice-btn {
  position: relative;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 1px solid var(--color-border, #E5E7EB);
  background: #fff;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  transition: all 0.2s;
}
.voice-btn:hover { border-color: var(--color-primary, #3B82F6); }
.voice-btn.recording {
  background: #FEE2E2;
  border-color: #DC2626;
  animation: pulse 1.4s ease-in-out infinite;
}
.voice-btn.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.dot {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 8px;
  height: 8px;
  background: #DC2626;
  border-radius: 50%;
  animation: blink 1s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.6); }
  50% { box-shadow: 0 0 0 8px rgba(220, 38, 38, 0); }
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
