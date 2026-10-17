<!-- components/ChatText.vue — 聊天气泡里的正文,记账聊天和投资顾问共用

     负责三件事:轻量 markdown(加粗 / 行内代码 / 列表 / 换行)、
     流式输出时的打字光标、正文出来之前的进度提示("思考中…")。 -->
<template>
  <div class="ct">
    <span v-if="streaming && !content" class="ct-status">
      {{ status || '思考中…' }}<i class="ct-dots"><b></b><b></b><b></b></i>
    </span>
    <span v-else v-html="html"></span>
    <span v-if="streaming && content" class="ct-caret" aria-hidden="true">▋</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  content: { type: String, default: '' },
  streaming: { type: Boolean, default: false },
  status: { type: String, default: '' },
})

function render(md) {
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc(md)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^[-•] (.+)$/gm, '<li>$1</li>')
    .replace(/((?:<li>.*<\/li>\n?)+)/g, (m) => `<ul>${m.replace(/\n/g, '')}</ul>`)
    .replace(/\n/g, '<br/>')
}

const html = computed(() => render(props.content || ''))
</script>

<style scoped>
.ct { white-space: normal; word-break: break-word; }
.ct :deep(ul) { margin: 4px 0; padding-left: 1.2em; }
.ct :deep(code) {
  padding: 0 4px; border-radius: 4px; font-size: .92em;
  background: rgba(0, 0, 0, .06);
}
.ct-status { color: var(--color-text-muted); }
.ct-dots { display: inline-flex; gap: 3px; margin-left: 4px; vertical-align: middle; }
.ct-dots b {
  width: 4px; height: 4px; border-radius: 50%; background: currentColor;
  animation: ct-dot 1.2s infinite ease-in-out;
}
.ct-dots b:nth-child(2) { animation-delay: .15s; }
.ct-dots b:nth-child(3) { animation-delay: .3s; }
@keyframes ct-dot { 0%, 80%, 100% { opacity: .25; } 40% { opacity: 1; } }
.ct-caret {
  display: inline-block; margin-left: 1px;
  color: var(--color-primary);
  animation: ct-blink 1s steps(1) infinite;
}
@keyframes ct-blink { 50% { opacity: 0; } }
</style>
