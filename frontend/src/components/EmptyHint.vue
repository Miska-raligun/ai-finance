<template>
  <div class="empty-hint" role="status">
    <!-- 装饰 SVG：小岛 + 椰子树 + 信封三选一，从 kind prop 决定 -->
    <svg v-if="kind === 'island'" class="empty-art" viewBox="0 0 200 140" aria-hidden="true">
      <!-- 海 -->
      <ellipse cx="100" cy="120" rx="90" ry="10" fill="#19c8b9" opacity="0.25"/>
      <!-- 小岛沙地 -->
      <ellipse cx="100" cy="110" rx="60" ry="14" fill="#f7cd67"/>
      <!-- 棕榈树干 -->
      <path d="M97 96 Q 95 80 100 65" stroke="#794f27" stroke-width="5" fill="none" stroke-linecap="round"/>
      <!-- 叶子 -->
      <ellipse cx="92" cy="62" rx="14" ry="6" fill="#6fba2c" transform="rotate(-25 92 62)"/>
      <ellipse cx="108" cy="62" rx="14" ry="6" fill="#82d23e" transform="rotate(25 108 62)"/>
      <ellipse cx="100" cy="55" rx="13" ry="6" fill="#86d67a"/>
      <!-- 椰子 -->
      <circle cx="98" cy="68" r="2.5" fill="#794f27"/>
      <!-- 几只小海鸟 -->
      <path d="M30 40 q 4 -3 8 0 q 4 -3 8 0" stroke="#9f927d" stroke-width="1.5" fill="none" stroke-linecap="round"/>
      <path d="M150 32 q 3 -2 6 0 q 3 -2 6 0" stroke="#9f927d" stroke-width="1.5" fill="none" stroke-linecap="round"/>
    </svg>

    <svg v-else-if="kind === 'letter'" class="empty-art" viewBox="0 0 200 140" aria-hidden="true">
      <!-- 信封 -->
      <rect x="50" y="50" width="100" height="70" rx="6" fill="#f8a6b2"/>
      <rect x="50" y="50" width="100" height="70" rx="6" fill="none" stroke="#794f27" stroke-width="2"/>
      <path d="M50 56 L100 90 L150 56" stroke="#794f27" stroke-width="2" fill="none"/>
      <!-- 心形封口 -->
      <path d="M100 85 q -6 -7 -12 -2 q -6 5 0 10 q 4 4 12 8 q 8 -4 12 -8 q 6 -5 0 -10 q -6 -5 -12 2 Z"
            fill="#fc736d" stroke="#c94444" stroke-width="1.5"/>
      <!-- 飞过的小鸟 -->
      <path d="M30 30 q 4 -3 8 0 q 4 -3 8 0" stroke="#9f927d" stroke-width="1.5" fill="none" stroke-linecap="round"/>
    </svg>

    <svg v-else-if="kind === 'coin'" class="empty-art" viewBox="0 0 200 140" aria-hidden="true">
      <!-- 三枚硬币堆 -->
      <ellipse cx="100" cy="118" rx="55" ry="6" fill="#794f27" opacity="0.18"/>
      <g transform="translate(70 80)">
        <ellipse cx="20" cy="20" rx="22" ry="7" fill="#dba90e"/>
        <rect x="-2" y="14" width="44" height="6" fill="#dba90e"/>
        <ellipse cx="20" cy="14" rx="22" ry="7" fill="#f5c31c"/>
        <text x="20" y="18" text-anchor="middle" font-size="9" font-weight="900" fill="#794f27">¥</text>
      </g>
      <g transform="translate(85 60)">
        <ellipse cx="20" cy="20" rx="22" ry="7" fill="#dba90e"/>
        <rect x="-2" y="14" width="44" height="6" fill="#dba90e"/>
        <ellipse cx="20" cy="14" rx="22" ry="7" fill="#ffcc00"/>
        <text x="20" y="18" text-anchor="middle" font-size="9" font-weight="900" fill="#794f27">¥</text>
      </g>
      <g transform="translate(60 40)">
        <ellipse cx="20" cy="20" rx="22" ry="7" fill="#dba90e"/>
        <rect x="-2" y="14" width="44" height="6" fill="#dba90e"/>
        <ellipse cx="20" cy="14" rx="22" ry="7" fill="#ffd33d"/>
        <text x="20" y="18" text-anchor="middle" font-size="9" font-weight="900" fill="#794f27">¥</text>
      </g>
      <!-- ✨ 装饰星 -->
      <text x="30" y="48" font-size="14" fill="#19c8b9">✦</text>
      <text x="160" y="60" font-size="12" fill="#fc736d">✦</text>
    </svg>

    <svg v-else class="empty-art" viewBox="0 0 200 140" aria-hidden="true">
      <!-- 默认：小帐篷 / 营地 -->
      <ellipse cx="100" cy="120" rx="80" ry="8" fill="#19c8b9" opacity="0.18"/>
      <polygon points="100,55 60,115 140,115" fill="#fc736d"/>
      <polygon points="100,55 75,115 100,115" fill="#e05a5a" opacity="0.5"/>
      <rect x="92" y="95" width="16" height="20" fill="#794f27" rx="2"/>
      <circle cx="100" cy="55" r="4" fill="#ffcc00"/>
      <text x="55" y="40" font-size="14" fill="#19c8b9">✦</text>
      <text x="155" y="50" font-size="12" fill="#f8a6b2">✦</text>
    </svg>

    <div class="empty-text">
      <div class="empty-title">{{ title }}</div>
      <div v-if="hint" class="empty-sub">{{ hint }}</div>
      <slot />
    </div>
  </div>
</template>

<script setup>
defineProps({
  // 'island' | 'letter' | 'coin' | 'tent'
  kind: { type: String, default: 'island' },
  title: { type: String, default: '这里还空着' },
  hint: { type: String, default: '' },
})
</script>

<style scoped>
.empty-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 28px 16px 32px;
  text-align: center;
}
.empty-art {
  width: 200px;
  height: 140px;
  flex-shrink: 0;
  filter: drop-shadow(0 4px 6px rgba(114, 93, 66, 0.15));
}
.empty-text {
  max-width: 320px;
}
.empty-title {
  font-size: 15px;
  font-weight: 800;
  color: var(--color-text-strong);
  letter-spacing: 0.02em;
}
.empty-sub {
  margin-top: 6px;
  font-size: 13px;
  color: var(--color-text-muted);
  line-height: 1.6;
}
</style>
