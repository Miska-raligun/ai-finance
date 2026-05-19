<template>
  <div class="island-wrap" :class="{ 'is-complete': pct >= 100 }">
    <div class="island-scene" :aria-label="`进度 ${pct}%`">
      <!-- 天空 → 海洋 渐变背景 + 微微浮动的太阳 -->
      <div class="sky"></div>
      <div class="sun" aria-hidden="true"></div>

      <!-- 主岛 + 椰子树（始终在） -->
      <svg class="island-svg" viewBox="0 0 280 88" preserveAspectRatio="none" aria-hidden="true">
        <!-- 远景小岛 -->
        <ellipse cx="40" cy="74" rx="22" ry="6" fill="#cdb89a" opacity="0.7"/>
        <!-- 主岛沙地 -->
        <path d="M 70 78 Q 120 60 180 64 Q 230 66 240 80 L 240 88 L 70 88 Z"
              fill="#f1d59b" />
        <!-- 草皮 -->
        <path d="M 90 72 Q 130 60 175 66 Q 215 70 225 78 L 225 80 L 90 80 Z"
              fill="#86d67a" />
        <!-- 椰子树（永远显示 — 代表"刚开始的岛"） -->
        <g transform="translate(108,52)">
          <rect x="-1.5" y="6" width="3" height="14" fill="#6b4a2b" rx="1"/>
          <ellipse cx="-5" cy="6" rx="7" ry="3" fill="#3eaa6a"/>
          <ellipse cx="5"  cy="6" rx="7" ry="3" fill="#3eaa6a"/>
          <ellipse cx="0"  cy="2" rx="8" ry="3" fill="#4cc07e"/>
        </g>
      </svg>

      <!-- 海平面 — 高度随 progress 升高，到 100% 时几乎淹到顶（"全员归岛" 即可） -->
      <div class="sea" :style="{ height: seaHeight + '%' }">
        <div class="wave wave-1"></div>
        <div class="wave wave-2"></div>
      </div>

      <!-- 4 个里程碑动物：25 / 50 / 75 / 100，按 pct 解锁 -->
      <div
        v-for="(m, i) in milestones" :key="i"
        class="milestone"
        :class="{ unlocked: pct >= m.at }"
        :style="{ left: m.pos + '%' }"
        :title="pct >= m.at ? `已解锁：${m.name}` : `还差 ${m.at - pct}% 解锁 ${m.name}`"
      >
        <span class="milestone-emoji" aria-hidden="true">{{ m.emoji }}</span>
        <span class="milestone-flag" :style="{ background: m.color }">{{ m.at }}%</span>
      </div>

      <!-- 100% 烟花点缀 -->
      <div v-if="pct >= 100" class="fireworks" aria-hidden="true">
        <span class="spark sp-1">✨</span>
        <span class="spark sp-2">🎉</span>
        <span class="spark sp-3">✨</span>
      </div>
    </div>

    <!-- 数值条：保留传统数字 + 百分比读数（无障碍 / 习惯） -->
    <div class="island-numline">
      <div class="num-fill" :style="{ width: pct + '%', background: barColor }"></div>
      <span class="num-pct" :class="{ inverted: pct >= 60 }">
        {{ pct }}%
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  current: { type: Number, default: 0 },
  target: { type: Number, default: 0 },
})

const pct = computed(() => {
  if (!props.target) return 0
  return Math.min(100, Math.max(0, Math.round(props.current / props.target * 100)))
})

// 海平面只升到 60% — 不然会盖掉所有里程碑动物
const seaHeight = computed(() => 18 + (pct.value / 100) * 42)

const milestones = [
  { at: 25,  pos: 25, emoji: '🐢', name: '海龟登岛',     color: '#7dd9cc' },
  { at: 50,  pos: 47, emoji: '🦊', name: '小狐狸来访',   color: '#f7cd67' },
  { at: 75,  pos: 70, emoji: '🦌', name: '麋鹿安家',     color: '#e59266' },
  { at: 100, pos: 92, emoji: '🦋', name: '蝴蝶 & 烟花',  color: '#b77dee' },
]

const barColor = computed(() => {
  if (pct.value >= 100) return 'linear-gradient(90deg,#86d67a,#19c8b9)'
  if (pct.value >= 60)  return 'linear-gradient(90deg,#19c8b9,#0a8a7e)'
  if (pct.value >= 30)  return 'linear-gradient(90deg,#82dfd2,#19c8b9)'
  return 'linear-gradient(90deg,#f7cd67,#f5c31c)'
})
</script>

<style scoped>
.island-wrap {
  --shore: #f1d59b;
  --sea: #19c8b9;
  --sea-deep: #0a8a7e;
  display: flex;
  flex-direction: column;
  gap: 6px;
  user-select: none;
}

.island-scene {
  position: relative;
  width: 100%;
  height: 88px;
  border-radius: 14px;
  overflow: hidden;
  background: linear-gradient(180deg, #e6f9f6 0%, #d4f0eb 40%, #b8e6dd 60%, #19c8b9 60%);
  box-shadow: inset 0 0 0 1px rgba(0,0,0,0.04), inset 0 -2px 0 rgba(0,0,0,0.04);
}
.is-complete .island-scene {
  background: linear-gradient(180deg, #fff6d0 0%, #ffe6a8 40%, #ffd57a 60%, #19c8b9 60%);
  animation: complete-glow 2.4s ease-in-out infinite;
}
@keyframes complete-glow {
  0%, 100% { box-shadow: inset 0 0 0 1px rgba(245, 195, 28, 0.4), 0 0 0 0 rgba(245, 195, 28, 0); }
  50% { box-shadow: inset 0 0 0 1px rgba(245, 195, 28, 0.6), 0 0 12px 2px rgba(245, 195, 28, 0.3); }
}

.sky {
  position: absolute; inset: 0;
  pointer-events: none;
}
.sun {
  position: absolute;
  top: 6px; right: 14px;
  width: 18px; height: 18px;
  border-radius: 50%;
  background: radial-gradient(circle, #fff2a8 0%, #ffd75a 70%, transparent 71%);
  box-shadow: 0 0 12px 2px rgba(255, 215, 90, 0.5);
  animation: sun-bob 4s ease-in-out infinite;
}
@keyframes sun-bob {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-2px); }
}

.island-svg {
  position: absolute;
  left: 0; right: 0; bottom: 0;
  width: 100%; height: 88px;
  pointer-events: none;
}

.sea {
  position: absolute;
  left: 0; right: 0; bottom: 0;
  background: linear-gradient(180deg, rgba(25, 200, 185, 0.55) 0%, rgba(10, 138, 126, 0.85) 100%);
  transition: height 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
  overflow: hidden;
  pointer-events: none;
}
.wave {
  position: absolute;
  top: -3px; left: -50%;
  width: 200%; height: 6px;
  background: radial-gradient(circle at 50% 0,
                              transparent 0,
                              transparent 4px,
                              rgba(255,255,255,0.45) 5px,
                              rgba(255,255,255,0.45) 6px,
                              transparent 7px);
  background-size: 14px 6px;
  background-repeat: repeat-x;
  animation: wave-flow 4s linear infinite;
}
.wave-2 {
  top: -1px;
  background-size: 22px 6px;
  opacity: 0.5;
  animation-duration: 6s;
  animation-direction: reverse;
}
@keyframes wave-flow {
  0% { transform: translateX(0); }
  100% { transform: translateX(50%); }
}

.milestone {
  position: absolute;
  bottom: 2px;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  filter: grayscale(1);
  opacity: 0.55;
  transition: filter 0.4s, opacity 0.4s, transform 0.4s;
  pointer-events: auto;
  cursor: help;
}
.milestone.unlocked {
  filter: grayscale(0);
  opacity: 1;
  transform: translateX(-50%) translateY(-2px);
  animation: bob 2.4s ease-in-out infinite;
}
@keyframes bob {
  0%, 100% { transform: translateX(-50%) translateY(-2px); }
  50%      { transform: translateX(-50%) translateY(-5px); }
}
.milestone-emoji {
  font-size: 20px;
  line-height: 1;
  text-shadow: 0 1px 2px rgba(0,0,0,0.15);
}
.milestone-flag {
  margin-top: 2px;
  padding: 0 5px;
  font-size: 9px;
  font-weight: 800;
  color: #fff;
  border-radius: 10px;
  letter-spacing: 0.02em;
  box-shadow: 0 1px 0 rgba(0,0,0,0.15);
}

.fireworks {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.spark {
  position: absolute;
  font-size: 16px;
  animation: spark-pop 2s ease-out infinite;
  opacity: 0;
}
.sp-1 { top: 10px; left: 22%; animation-delay: 0s; }
.sp-2 { top: 6px;  left: 55%; font-size: 22px; animation-delay: 0.6s; }
.sp-3 { top: 14px; left: 80%; animation-delay: 1.2s; }
@keyframes spark-pop {
  0%   { opacity: 0; transform: scale(0.4) translateY(8px); }
  30%  { opacity: 1; transform: scale(1.1) translateY(0); }
  70%  { opacity: 0.6; transform: scale(1) translateY(-2px); }
  100% { opacity: 0; transform: scale(0.7) translateY(-8px); }
}

.island-numline {
  position: relative;
  height: 8px;
  border-radius: 50px;
  background: #ebedf0;
  overflow: hidden;
  box-shadow: inset 0 1px 2px rgba(0,0,0,0.08);
}
.num-fill {
  position: absolute;
  left: 0; top: 0; bottom: 0;
  border-radius: 50px;
  transition: width 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
  box-shadow: inset 0 -1px 0 rgba(0,0,0,0.1);
}
.num-pct {
  position: absolute;
  right: 6px; top: 50%;
  transform: translateY(-50%);
  font-size: 10px;
  font-weight: 800;
  color: var(--color-text);
  font-variant-numeric: tabular-nums;
}
.num-pct.inverted { color: #fff; right: auto; left: 6px; }

/* 小屏：缩小一点免得太占空间 */
@media (max-width: 480px) {
  .island-scene { height: 76px; }
  .milestone-emoji { font-size: 17px; }
  .milestone-flag { font-size: 8px; }
}

/* 减少动画偏好 */
@media (prefers-reduced-motion: reduce) {
  .sun, .milestone.unlocked, .wave, .wave-2, .spark, .is-complete .island-scene {
    animation: none !important;
  }
  .sea, .num-fill { transition: none !important; }
}
</style>
