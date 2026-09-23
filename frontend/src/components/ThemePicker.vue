<template>
  <el-dialog
    v-model="visible"
    title="🎨 主题切换"
    :width="dialogWidth"
    append-to-body
    @close="$emit('close')"
  >
    <div class="theme-list">
      <button
        v-for="t in THEMES"
        :key="t.value"
        class="theme-card"
        :class="{ active: current === t.value }"
        :style="t.preview"
        @click="apply(t.value)"
      >
        <span class="theme-emoji" aria-hidden="true">{{ t.emoji }}</span>
        <span class="theme-name">{{ t.label }}</span>
        <span v-if="current === t.value" class="theme-check">✓</span>
      </button>
    </div>
    <div class="theme-foot">
      <el-checkbox v-model="auto" @change="onAutoChange" class="theme-auto-cb">
        <span class="auto-label">
          <span class="auto-title">按季节自动切换</span>
          <span class="auto-detail">3-5 春樱 · 6-8 夏海 · 9-11 秋叶 · 12-2 冬雪</span>
        </span>
      </el-checkbox>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'close'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const _mq = window.matchMedia('(max-width: 768px)')
const isMobile = ref(_mq.matches)
function _onMq(e) { isMobile.value = e.matches }
onMounted(() => _mq.addEventListener('change', _onMq))
onBeforeUnmount(() => _mq.removeEventListener('change', _onMq))
const dialogWidth = computed(() => isMobile.value ? 'calc(100vw - 32px)' : '480px')

const THEMES = [
  { value: 'default', emoji: '🌴', label: '默认（暖米）',
    preview: { background: 'linear-gradient(135deg, #f8f8f0, #e6f9f6)', color: '#725d42' } },
  { value: 'dark',    emoji: '🌙', label: '夜晚岛屿',
    preview: { background: 'linear-gradient(135deg, #2b2118, #3d3028)', color: '#f0e3cf' } },
  { value: 'spring',  emoji: '🌸', label: '春樱',
    preview: { background: 'linear-gradient(135deg, #fff5f5, #ffe0ec)', color: '#99355a' } },
  { value: 'summer',  emoji: '🌊', label: '夏海',
    preview: { background: 'linear-gradient(135deg, #f0faff, #cdf0fa)', color: '#0e3a55' } },
  { value: 'autumn',  emoji: '🍁', label: '秋叶',
    preview: { background: 'linear-gradient(135deg, #fff5e6, #fde2c9)', color: '#8c3d12' } },
  { value: 'winter',  emoji: '❄️', label: '冬雪',
    preview: { background: 'linear-gradient(135deg, #f4f6fb, #dfe5f5)', color: '#1f2c4f' } },
]

const current = ref(localStorage.getItem('theme') || 'default')
const auto = ref(localStorage.getItem('theme_auto') === '1')

function apply(v) {
  current.value = v
  // 手动选 = 关闭自动
  if (auto.value) {
    auto.value = false
    localStorage.removeItem('theme_auto')
  }
  setTheme(v, /*persist*/ true)
}

function onAutoChange(v) {
  if (v) {
    localStorage.setItem('theme_auto', '1')
    const seasonal = currentSeasonTheme()
    current.value = seasonal
    setTheme(seasonal, /*persist*/ false)  // 自动模式不存 theme，下次重启再算
  } else {
    localStorage.removeItem('theme_auto')
  }
}

function setTheme(v, persist) {
  if (v === 'default') {
    document.body.removeAttribute('data-theme')
  } else {
    document.body.setAttribute('data-theme', v)
  }
  if (persist) localStorage.setItem('theme', v)
}

function currentSeasonTheme() {
  const m = new Date().getMonth() + 1  // 1..12
  if (m >= 3 && m <= 5)  return 'spring'
  if (m >= 6 && m <= 8)  return 'summer'
  if (m >= 9 && m <= 11) return 'autumn'
  return 'winter'
}

// 进入应用时即时应用保存的主题（脚本入口同步执行）
const stored = auto.value ? currentSeasonTheme() : current.value
setTheme(stored, false)
</script>

<style scoped>
.theme-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
}
.theme-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 18px 12px;
  border-radius: 16px;
  border: 2.5px solid transparent;
  cursor: pointer;
  font-family: inherit;
  box-shadow: 0 3px 0 0 rgba(0,0,0,0.12);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  min-height: 88px;
}
.theme-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 5px 0 0 rgba(0,0,0,0.18);
}
.theme-card.active {
  border-color: var(--color-primary);
}
.theme-emoji { font-size: 24px; }
.theme-name {
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-align: center;
  white-space: nowrap;
}
.theme-check {
  position: absolute;
  top: 6px;
  right: 10px;
  font-size: 13px;
  font-weight: 900;
  color: var(--color-primary);
}
.theme-foot {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border-light);
  font-size: 13px;
}

/* 让 checkbox 内部允许两行：标题 + 详细描述 */
.theme-auto-cb :deep(.el-checkbox__label) {
  white-space: normal;
  line-height: 1.4;
}
.auto-label {
  display: inline-flex;
  flex-direction: column;
  gap: 2px;
}
.auto-title {
  font-weight: 700;
  color: var(--color-text);
}
.auto-detail {
  font-size: 11px;
  color: var(--color-text-muted);
  letter-spacing: 0.02em;
}

/* 移动端：磁贴更小、文字更紧凑，让 2 列也能放下 */
@media (max-width: 480px) {
  .theme-list {
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
  }
  .theme-card {
    padding: 14px 8px;
    min-height: 78px;
    border-radius: 14px;
  }
  .theme-emoji { font-size: 20px; }
  .theme-name {
    font-size: 11px;
    letter-spacing: 0.02em;
  }
  .auto-detail { font-size: 10px; }
}
</style>
