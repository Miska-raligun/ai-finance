<template>
  <div class="home-page">
    <header class="home-header">
      <img src="/favicon.ico" class="home-avatar" alt="Anon 助手头像">
      <div class="home-greeting">
        <div class="home-hello">你好，{{ userStore.username || '朋友' }} 👋</div>
        <div class="home-sub">今天想做点什么呢？</div>
      </div>
    </header>

    <main class="phone-grid" aria-label="功能入口">
      <button
        v-for="tile in visibleTiles"
        :key="tile.path"
        class="phone-tile"
        :style="{ background: tile.color }"
        @click="go(tile.path)"
      >
        <span class="tile-emoji" aria-hidden="true">{{ tile.emoji }}</span>
        <span class="tile-label">{{ tile.label }}</span>
      </button>
    </main>

    <!-- 海浪 + 树装饰 -->
    <footer class="home-footer">
      <img src="@/assets/decor/tree.svg" class="footer-tree footer-tree-left" alt="">
      <div class="footer-wave"></div>
      <img src="@/assets/decor/tree.svg" class="footer-tree footer-tree-right" alt="">
    </footer>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

// NookPhone 13 色调色板里抽出来用作磁贴背景
const TILES = [
  { path: '/chat', label: '聊天记账', emoji: '💬', color: '#82d5bb' },
  { path: '/ledger', label: '账本管理', emoji: '📒', color: '#f7cd67' },
  { path: '/investment', label: '投资理财', emoji: '📈', color: '#889df0' },
  { path: '/reports', label: '月度报告', emoji: '📑', color: '#f8a6b2' },
  { path: '/admin', label: '用户管理', emoji: '🛠', color: '#e59266', adminOnly: true },
]

const visibleTiles = computed(() =>
  TILES.filter(t => !t.adminOnly || userStore.isAdmin),
)

function go(path) {
  router.push(path)
}
</script>

<style scoped>
.home-page {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: calc(100dvh - var(--topbar-height));
  padding: 32px 20px 0;
  position: relative;
  overflow: hidden;
}

.home-header {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  max-width: 480px;
  margin-bottom: 36px;
}
.home-avatar {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: #fff;
  border: 3px solid var(--color-surface);
  box-shadow: 0 4px 0 0 var(--shadow-anchor);
  transition: transform 0.2s ease;
}
.home-avatar:hover { transform: rotate(-5deg) scale(1.05); }

.home-greeting { flex: 1; }
.home-hello {
  font-size: 18px;
  font-weight: 800;
  color: var(--color-text-strong);
  letter-spacing: 0.02em;
}
.home-sub {
  font-size: 13px;
  color: var(--color-text-muted);
  margin-top: 2px;
}

.phone-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 18px;
  width: 100%;
  max-width: 480px;
}

.phone-tile {
  aspect-ratio: 1 / 1;
  border-radius: var(--radius-tile-large);
  border: 2.5px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 6px 0 0 var(--shadow-anchor);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  transition:
    transform 0.18s cubic-bezier(0.4, 0, 0.2, 1),
    box-shadow 0.18s cubic-bezier(0.4, 0, 0.2, 1);
  padding: 12px;
}
.phone-tile:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 0 0 var(--shadow-anchor);
}
.phone-tile:active {
  transform: translateY(3px);
  box-shadow: 0 2px 0 0 var(--shadow-anchor);
}

.tile-emoji {
  font-size: 36px;
  filter: drop-shadow(0 2px 2px rgba(0,0,0,0.15));
}
.tile-label {
  font-size: 13px;
  font-weight: 700;
  color: #3b2419;
  text-shadow: 0 1px 0 rgba(255,255,255,0.4);
  letter-spacing: 0.02em;
}

.home-footer {
  position: relative;
  width: 100%;
  margin-top: auto;
  height: 100px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  pointer-events: none;
}
.footer-tree {
  height: 60px;
  filter: drop-shadow(0 3px 4px rgba(0,0,0,0.12));
  z-index: 1;
}
.footer-tree-left { margin-left: 12px; }
.footer-tree-right { margin-right: 12px; transform: scaleX(-1); }
.footer-wave {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 60px;
  background: url('@/assets/decor/wave.svg') repeat-x bottom / 240px 60px;
}

@media (max-width: 380px) {
  .phone-grid { gap: 12px; }
  .tile-emoji { font-size: 28px; }
  .tile-label { font-size: 11px; }
}
</style>
