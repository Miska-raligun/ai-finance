<template>
  <div class="home-page">
    <div class="home-inner">
      <header class="home-header">
        <img src="/favicon.ico" class="home-avatar" alt="Anon 助手头像">
        <div class="home-greeting">
          <div class="home-hello">{{ greeting }}，{{ userStore.username || '朋友' }} 👋</div>
          <div class="home-sub">{{ dateLine }} · 今天想做点什么呢？</div>
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

      <main class="tile-grid" aria-label="功能入口">
        <button
          v-for="(tile, idx) in visibleTiles"
          :key="tile.path"
          class="tile-card animal-pop"
          :style="{ background: tile.color, '--i': idx }"
          @click="go(tile.path)"
        >
          <span class="tile-avatar-ring">
            <img :src="tile.avatar" class="tile-avatar" alt="" aria-hidden="true">
          </span>
          <span class="tile-text">
            <span class="tile-label">{{ tile.label }}</span>
            <span class="tile-desc">{{ tile.desc }}</span>
          </span>
          <span class="tile-arrow" aria-hidden="true">›</span>
        </button>
      </main>
    </div>

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

// NookPhone 13 色调色板里抽出来用作卡片背景；avatar 与 sidebar 同款小动物
const TILES = [
  { path: '/chat',       label: '聊天记账', desc: '打字 / 拍照 / 语音，说一句就记上', avatar: iconBunny,  color: '#82d5bb' },
  { path: '/ledger',     label: '账本管理', desc: '收支明细 · 预算 · 图表',           avatar: iconShiba,  color: '#f7cd67' },
  { path: '/investment', label: '投资理财', desc: '持仓 · 攒钱目标 · AI 顾问',        avatar: iconOwl,    color: '#889df0' },
  { path: '/reports',    label: '月度报告', desc: 'AI 月报和本月回顾卡',              avatar: iconBeaver, color: '#f8a6b2' },
  { path: '/admin',      label: '用户管理', desc: '用户与 LLM 用量看板',              avatar: iconFox,    color: '#e59266', adminOnly: true },
]

const visibleTiles = computed(() =>
  TILES.filter(t => !t.adminOnly || userStore.isAdmin),
)

// 问候语随时段变化,比一成不变的"你好"更像有人在等你回来
const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 5) return '夜深了'
  if (h < 11) return '早上好'
  if (h < 13) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

const dateLine = new Date().toLocaleDateString('zh-CN', {
  month: 'long', day: 'numeric', weekday: 'long',
})

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
  padding: 28px 20px 0;
  position: relative;
  overflow: hidden;
}

/* 内容列：桌面拉宽到 720px,不再是"放大的手机屏" */
.home-inner {
  width: 100%;
  max-width: 720px;
  display: flex;
  flex-direction: column;
}

.home-header {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 22px;
}
.home-avatar {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: #fff;
  border: 3px solid var(--color-surface);
  box-shadow: 0 4px 0 0 var(--shadow-anchor);
  transition: transform 0.2s ease;
}
.home-avatar:hover { transform: rotate(-5deg) scale(1.05); }

.home-hello {
  font-size: 19px;
  font-weight: 800;
  color: var(--color-text-strong);
  letter-spacing: 0.02em;
}
.home-sub {
  font-size: 13px;
  color: var(--color-text-muted);
  margin-top: 3px;
}

.home-glance {
  display: flex;
  align-items: center;
  justify-content: space-around;
  gap: 8px;
  margin-bottom: 22px;
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
  font-size: 18px;
  font-weight: 800;
  color: var(--color-text-strong);
  white-space: nowrap;
}
.glance-ok { color: #15803d; }
.glance-over { color: #e05a5a; }
.glance-divider {
  width: 1.5px;
  height: 30px;
  background: rgba(0, 0, 0, 0.08);
  flex-shrink: 0;
}
.glance-fade-enter-active { transition: opacity 0.3s ease, transform 0.3s ease; }
.glance-fade-enter-from { opacity: 0; transform: translateY(-6px); }

/* 功能卡片：横向卡(头像 + 标题/说明 + 箭头),桌面两列、手机一列 */
.tile-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}

.tile-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border-radius: var(--radius-tile-large, 20px);
  border: 2.5px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 5px 0 0 var(--shadow-anchor);
  cursor: pointer;
  text-align: left;
  transition:
    transform 0.18s cubic-bezier(0.4, 0, 0.2, 1),
    box-shadow 0.18s cubic-bezier(0.4, 0, 0.2, 1);
}
.tile-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 7px 0 0 var(--shadow-anchor);
}
.tile-card:active {
  transform: translateY(3px);
  box-shadow: 0 2px 0 0 var(--shadow-anchor);
}

.tile-avatar-ring {
  flex-shrink: 0;
  width: 52px;
  height: 52px;
  display: grid;
  place-items: center;
  background: rgba(255, 255, 255, 0.88);
  border-radius: 50%;
  box-shadow: 0 3px 0 0 rgba(0, 0, 0, 0.15);
  transition: transform 0.25s cubic-bezier(0.25, 1.2, 0.4, 1);
}
.tile-avatar {
  width: 40px;
  height: 40px;
}
.tile-card:hover .tile-avatar-ring {
  transform: scale(1.08) rotate(-6deg);
}
.tile-card:active .tile-avatar-ring {
  transform: scale(0.95) rotate(0);
}

.tile-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}
.tile-label {
  font-size: 15px;
  font-weight: 800;
  color: #3b2419;
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.4);
  letter-spacing: 0.02em;
}
.tile-desc {
  font-size: 12px;
  color: rgba(59, 36, 25, 0.66);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tile-arrow {
  flex-shrink: 0;
  font-size: 22px;
  font-weight: 800;
  color: rgba(59, 36, 25, 0.45);
  transition: transform 0.18s ease;
}
.tile-card:hover .tile-arrow { transform: translateX(3px); }

.home-footer {
  position: relative;
  width: 100%;
  margin-top: auto;
  height: 96px;
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

/* 手机：单列卡片列表,拇指好点,说明文字完整可读 */
@media (max-width: 560px) {
  .home-page { padding: 20px 14px 0; }
  .tile-grid { grid-template-columns: 1fr; gap: 11px; }
  .tile-card { padding: 12px 14px; }
  .tile-avatar-ring { width: 46px; height: 46px; }
  .tile-avatar { width: 35px; height: 35px; }
  .home-hello { font-size: 17px; }
  .home-avatar { width: 48px; height: 48px; }
  .glance-value { font-size: 16px; }
  .home-glance { padding: 12px 12px; margin-bottom: 18px; }
  .home-footer { height: 76px; }
  .footer-tree { height: 48px; }
}

/* 矮屏手机(SE 等):压缩留白,保证 5 张卡 + 速览不用滚动也能看全关键内容 */
@media (max-height: 700px) and (max-width: 560px) {
  .home-header { margin-bottom: 14px; }
  .home-glance { margin-bottom: 14px; }
  .home-footer { height: 52px; }
  .footer-tree { display: none; }
}
</style>
