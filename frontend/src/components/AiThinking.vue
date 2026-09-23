<template>
  <div class="aithinking">
    <div class="ai-avatar">
      <img :src="avatarSrc" alt="Anon" />
    </div>
    <div class="ai-bubble" :class="{ pulse: !cancelable }">
      <span class="ai-step">{{ currentStep }}</span>
      <span class="ai-dots"><i></i><i></i><i></i></span>
    </div>
    <el-button
      v-if="cancelable"
      size="small"
      round
      :disabled="!cancelable"
      @click="$emit('cancel')"
    >取消</el-button>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
// Anon 头像通过 Vite 资源导入拿到正确的 hashed URL（dev/prod 一致），
// 避免 /favicon.ico 在生产 404 的坑（见 RecapCard 同款做法）。
import anonUrl from '../../favicon.ico'

const props = defineProps({
  steps: {
    type: Array,
    default: () => ['🐾 正在收集你的财务数据', '🤔 Anon 正在分析', '✍️ 整理建议中…'],
  },
  intervalMs: { type: Number, default: 2500 },
  cancelable: { type: Boolean, default: true },
})

defineEmits(['cancel'])

const avatarSrc = ref(anonUrl)
const idx = ref(0)
const currentStep = ref(props.steps[0])
let timer = null

function startCycle() {
  stopCycle()
  idx.value = 0
  currentStep.value = props.steps[0]
  timer = setInterval(() => {
    idx.value = (idx.value + 1) % props.steps.length
    currentStep.value = props.steps[idx.value]
  }, props.intervalMs)
}

function stopCycle() {
  if (timer) { clearInterval(timer); timer = null }
}

onMounted(startCycle)
onBeforeUnmount(stopCycle)
watch(() => props.steps, startCycle)
</script>

<style scoped>
.aithinking {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: var(--color-surface-2, #f0ece2);
  border: 1.5px dashed var(--color-border, #c4b89e);
  border-radius: 14px;
}
.ai-avatar {
  width: 36px; height: 36px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--color-surface, #fff);
  border: 2px solid var(--color-border);
  overflow: hidden;
  animation: anon-bounce 1.6s ease-in-out infinite;
}
.ai-avatar img { width: 100%; height: 100%; object-fit: cover; display: block; }
.ai-bubble {
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text-strong, #794f27);
  min-width: 0;
}
.ai-step {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ai-dots { display: inline-flex; gap: 3px; }
.ai-dots i {
  width: 5px; height: 5px;
  border-radius: 50%;
  background: var(--color-primary, #19c8b9);
  animation: dot-blink 1.2s infinite;
}
.ai-dots i:nth-child(2) { animation-delay: 0.2s; }
.ai-dots i:nth-child(3) { animation-delay: 0.4s; }

@keyframes anon-bounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-3px); }
}
@keyframes dot-blink {
  0%, 60%, 100% { opacity: 0.25; }
  30% { opacity: 1; }
}
</style>
