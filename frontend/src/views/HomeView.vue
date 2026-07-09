<template>
  <div class="home-page">
    <header class="home-header">
      <img src="/favicon.ico" class="home-avatar" alt="Anon 助手头像">
      <div class="home-greeting">
        <div class="home-hello">你好，{{ userStore.username || '朋友' }} 👋</div>
        <div class="home-sub">今天想做点什么呢？</div>
      </div>
    </header>

    <!-- 今日速览：打开 App 第一眼先看到数据,而不是一排按钮 -->
    <transition name="glance-fade">
      <div v-if="glance" class="home-glance" role="button" @click="go('/ledger')">
        <div class="glance-item">
          <span class="glance-label">今天已花</span>
          <span class="glance-value">¥{{ fmt(glance.today_spend) }}</span>
        </div>
        <div class="glance-divider"></div>
        <div class="glance-item">
          <span class="glance-label">本月已花</span>
          <span class="glance-value">¥{{ fmt(glance.month_spend) }}</span>
        </div>
        <template v-if="glance.budget_remaining !== null">
          <div class="glance-divider"></div>
          <div class="glance-item">
            <span class="glance-label">预算还剩</span>
            <span :class="['glance-value', glance.budget_remaining < 0 ? 'glance-over' : 'glance-ok']">
              ¥{{ fmt(glance.budget_remaining) }}
            </span>
          </div>
        </template>
      </div>
    </transition>

    <main class="phone-grid" aria-label="功能入口">
      <button
        v-for="(tile, idx) in visibleTiles"
        :key="tile.path"
        class="phone-tile animal-pop"
        :style="{ background: tile.color, '--i': idx }"
        @click="go(tile.path)"
      >
        <img :src="tile.avatar" class="tile-avatar" alt="" aria-hidden="true">
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
import { computed, ref, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import api from '@/api'
import iconBunny from '@/assets/decor/avatars/bunny.svg'
import iconShiba from '@/assets/decor/avatars/shiba.svg'
import iconOwl from '@/assets/decor/avatars/owl.svg'
import iconBeaver from '@/assets/decor/avatars/beaver.svg'
import iconFox from '@/assets/decor/avatars/fox.svg'

const router = useRouter()
const userStore = useUserStore()

// NookPhone 13 色调色板里抽出来用作磁贴背景；avatar 与 sidebar 同款小动物
const TILES = [
  { path: '/chat',       label: '聊天记账', avatar: iconBunny,  color: '#82d5bb' },
  { path: '/ledger',     label: '账本管理', avatar: iconShiba,  color: '#f7cd67' },
  { path: '/investment', label: '投资理财', avatar: iconOwl,    color: '#889df0' },
  { path: '/reports',    label: '月度报告', avatar: iconBeaver, color: '#f8a6b2' },
  { path: '/admin',      label: '用户管理', avatar: iconFox,    color: '#e59266', adminOnly: true },
]

const visibleTiles = computed(() =>
  TILES.filter(t => !t.adminOnly || userStore.isAdmin),
)

function go(path) {
  router.push(path)
}

// 今日速览。拉不到就整条隐藏(silent),不打扰首页
const glance = ref(null)

function fmt(n) {
  const v = Number(n) || 0
  return Math.abs(v) >= 10000
    ? (v / 10000).toFixed(2) + '万'
    : v.toFixed(2)
}

async function loadGlance() {
  try {
    const res = await api.get('/api/stats/today', { silent: true })
    glance.value = res.data
  } catch {
    glance.value = null
  }
}

onMounted(loadGlance)
// keep-alive 切回首页时刷新,让刚记的账立刻反映在速览里
onActivated(loadGlance)
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

.home-glance {
  display: flex;
  align-items: center;
  justify-content: space-around;
  gap: 8px;
  width: 100%;
  max-width: 480px;
  margin: -16px 0 24px;
  padding: 14px 18px;
  background: var(--color-surface, #fff);
  border: 2.5px solid rgba(0, 0, 0, 0.08);
  border-radius: var(--radius-tile-large, 20px);
  box-shadow: 0 4px 0 0 var(--shadow-anchor);
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}
.home-glance:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 0 0 var(--shadow-anchor);
}
.glance-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-width: 0;
}
.glance-label {
  font-size: 11px;
  color: var(--color-text-muted);
  letter-spacing: 0.02em;
}
.glance-value {
  font-size: 17px;
  font-weight: 800;
  color: var(--color-text-strong);
  white-space: nowrap;
}
.glance-ok { color: #15803d; }
.glance-over { color: #e05a5a; }
.glance-divider {
  width: 1.5px;
  height: 28px;
  background: rgba(0, 0, 0, 0.08);
  flex-shrink: 0;
}
.glance-fade-enter-active { transition: opacity 0.3s ease, transform 0.3s ease; }
.glance-fade-enter-from { opacity: 0; transform: translateY(-6px); }

@media (max-width: 380px) {
  .glance-value { font-size: 15px; }
  .home-glance { padding: 12px 12px; }
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
.tile-avatar {
  width: 56px;
  height: 56px;
  background: rgba(255,255,255,0.85);
  border-radius: 50%;
  padding: 4px;
  box-shadow: 0 3px 0 0 rgba(0,0,0,0.18);
  transition: transform 0.25s cubic-bezier(0.25, 1.2, 0.4, 1);
}
.phone-tile:hover .tile-avatar {
  transform: scale(1.08) rotate(-6deg);
}
.phone-tile:active .tile-avatar {
  transform: scale(0.95) rotate(0);
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
  .tile-avatar { width: 44px; height: 44px; padding: 3px; }
  .tile-label { font-size: 11px; }
}
</style>
