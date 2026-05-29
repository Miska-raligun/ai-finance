<template>
  <div class="recap-wrap">
    <div v-if="loading" class="recap-loading">
      <el-skeleton :rows="5" animated />
    </div>

    <template v-else-if="recap && recap.source === 'empty'">
      <EmptyHint
        kind="letter"
        title="这个月还没有账本回顾"
        :hint="recap.caption || '记几笔再来看看本月回顾卡片吧～'"
      />
    </template>

    <template v-else-if="recap">
      <!-- 导出范围：cardRef；PC 横版、移动端竖版 -->
      <div ref="cardRef" class="recap-card" :class="isMobile ? 'is-mobile' : 'is-pc'">
        <div class="recap-deco" aria-hidden="true"></div>

        <div class="recap-left">
          <header class="recap-head">
            <div class="recap-title">
              <span class="recap-emoji">🐾</span>
              <div>
                <div class="recap-kicker">本月回顾</div>
                <div class="recap-period">{{ recap.period }}</div>
              </div>
            </div>
            <img :src="anonSrc" class="recap-anon" alt="Anon" />
          </header>

          <div class="recap-caption">{{ recap.caption }}</div>

          <div class="recap-kpis">
            <div class="kpi-row">
              <span class="kpi-label">总支出</span>
              <span class="kpi-value spend">¥{{ fmt(recap.spend_total) }}</span>
            </div>
            <div class="kpi-row">
              <span class="kpi-label">总收入</span>
              <span class="kpi-value income">¥{{ fmt(recap.income_total) }}</span>
            </div>
            <div class="kpi-row">
              <span class="kpi-label">净结余</span>
              <span class="kpi-value" :class="recap.net >= 0 ? 'income' : 'spend'">¥{{ fmt(Math.abs(recap.net)) }}</span>
            </div>
          </div>
        </div>

        <div class="recap-right">
          <div class="recap-tiles">
            <div v-if="recap.largest_txn" class="tile">
              <span class="tile-ico">💸</span>
              <div class="tile-body">
                <div class="tile-label">最大单笔</div>
                <div class="tile-main">¥{{ fmt(recap.largest_txn.amount) }}</div>
                <div class="tile-sub">{{ recap.largest_txn.category }}<template v-if="recap.largest_txn.note"> · {{ recap.largest_txn.note }}</template></div>
              </div>
            </div>

            <div v-if="recap.highest_day" class="tile">
              <span class="tile-ico">📅</span>
              <div class="tile-body">
                <div class="tile-label">花得最多的一天</div>
                <div class="tile-main">{{ recap.highest_day.date.slice(5) }}</div>
                <div class="tile-sub">当天 ¥{{ fmt(recap.highest_day.total) }}</div>
              </div>
            </div>

            <div v-if="recap.top_category" class="tile">
              <span class="tile-ico">🏆</span>
              <div class="tile-body">
                <div class="tile-label">最舍得花的分类</div>
                <div class="tile-main">{{ recap.top_category.category }}</div>
                <div class="tile-sub">¥{{ fmt(recap.top_category.total) }} · {{ recap.top_category.cnt }} 笔</div>
              </div>
            </div>

            <div class="tile">
              <span class="tile-ico">🔥</span>
              <div class="tile-body">
                <div class="tile-label">连续记账</div>
                <div class="tile-main">{{ recap.streak }} 天</div>
                <div class="tile-sub">本月记账 {{ recap.active_days }} 天 · 共 {{ recap.record_count }} 笔</div>
              </div>
            </div>

            <div v-if="recap.mom && recap.mom.change_pct !== null" class="tile">
              <span class="tile-ico">{{ recap.mom.change_pct <= 0 ? '🟢' : '🔴' }}</span>
              <div class="tile-body">
                <div class="tile-label">支出环比</div>
                <div class="tile-main" :class="recap.mom.change_pct <= 0 ? 'income' : 'spend'">
                  {{ recap.mom.change_pct >= 0 ? '↑' : '↓' }} {{ Math.abs(recap.mom.change_pct) }}%
                </div>
                <div class="tile-sub">上月 ¥{{ fmt(recap.mom.prev_spend) }}</div>
              </div>
            </div>
          </div>

          <footer class="recap-foot">由 Anon 生成 · 数据来自你本月的真实记账 🌿</footer>
        </div>
      </div>

      <div class="recap-actions">
        <span v-if="recap.source === 'fallback'" class="recap-tag">本地文案</span>
        <el-button :loading="exporting" round @click="exportPng">📸 导出图片分享</el-button>
      </div>
    </template>

    <EmptyHint v-else kind="letter" title="选择月份生成回顾" hint="点上方月份，Anon 帮你做一张本月回顾卡片。" />
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { domToPng } from 'modern-screenshot'
import EmptyHint from '@/components/EmptyHint.vue'
// 通过 Vite 资源导入拿到 favicon 的正确 URL（dev 是 /favicon.ico，prod 是带 hash 的
// /assets/favicon-xxxx.ico）——硬编码 '/favicon.ico' 在生产构建里会 404。
import anonUrl from '../../favicon.ico'

const props = defineProps({
  recap: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})

const cardRef = ref(null)
const exporting = ref(false)

const _mq = window.matchMedia('(max-width: 768px)')
const isMobile = ref(_mq.matches)
function _onMq(e) { isMobile.value = e.matches }

// Anon 头像：预先把 favicon 转成 data URL 内联进卡片，导出时无需再抓外部图。
const anonSrc = ref(anonUrl)
async function _inlineAnon() {
  try {
    const res = await fetch(anonUrl, { cache: 'force-cache' })
    const blob = await res.blob()
    // 防 SPA 404 兜底返回 index.html：拿到的不是图片就不替换，继续用资源 URL。
    if (!blob.type.startsWith('image')) return
    anonSrc.value = await new Promise((resolve, reject) => {
      const fr = new FileReader()
      fr.onload = () => resolve(fr.result)
      fr.onerror = reject
      fr.readAsDataURL(blob)
    })
  } catch { /* 抓取失败就退回资源 URL */ }
}

onMounted(() => {
  _mq.addEventListener('change', _onMq)
  _inlineAnon()
})
onBeforeUnmount(() => _mq.removeEventListener('change', _onMq))

function fmt(n) {
  if (n == null) return '0.00'
  return Number(n).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function exportPng() {
  const node = cardRef.value
  if (!node) return
  exporting.value = true
  try {
    if (document.fonts && document.fonts.ready) {
      try { await document.fonts.ready } catch { /* ignore */ }
    }
    const bg = getComputedStyle(document.body).getPropertyValue('--color-surface').trim() || '#f7f3df'
    // modern-screenshot：相比 html-to-image 对资源 / webfont 的预加载更完整，
    // 单次调用即可拿到完整截图，速度也更快。
    const dataUrl = await domToPng(node, {
      scale: 2,
      backgroundColor: bg,
      width: node.scrollWidth,
      height: node.scrollHeight,
    })
    const a = document.createElement('a')
    a.href = dataUrl
    a.download = `回顾_${props.recap?.period || ''}.png`
    a.click()
  } catch (e) {
    console.error('recap export failed', e)
    ElMessage.error('导出失败，请重试')
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.recap-wrap { width: 100%; }
.recap-loading { padding: 16px; }

.recap-card {
  position: relative;
  overflow: hidden;
  margin: 0 auto;
  box-sizing: border-box;
  border-radius: var(--radius-card, 20px);
  background:
    radial-gradient(120% 80% at 100% 0%, var(--color-primary-light, #e6f9f6) 0%, transparent 55%),
    var(--color-surface, #f7f3df);
  border: 2px solid var(--color-border, #c4b89e);
  box-shadow: var(--shadow-card, 0 4px 10px rgba(107,92,67,0.18));
}

/* 移动端：竖版单列，撑满可用宽度 */
.recap-card.is-mobile {
  width: 100%;
  max-width: 480px;
  padding: 20px 18px 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* PC：横版，左信息 + 右亮点，整体更大 */
.recap-card.is-pc {
  display: flex;
  flex-direction: row;
  align-items: stretch;
  gap: 24px;
  max-width: 840px;
  padding: 28px 30px 24px;
}
.recap-card.is-pc .recap-left { flex: 0 0 312px; }
.recap-card.is-pc .recap-right { flex: 1 1 auto; }

.recap-left, .recap-right {
  position: relative;
  z-index: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.recap-deco {
  position: absolute;
  right: -30px;
  bottom: -30px;
  width: 150px;
  height: 150px;
  border-radius: 50%;
  background: var(--color-primary-light, #e6f9f6);
  opacity: 0.45;
  pointer-events: none;
  z-index: 0;
}

.recap-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.recap-title { display: flex; align-items: center; gap: 10px; min-width: 0; }
.recap-emoji { font-size: 30px; flex-shrink: 0; }
.recap-kicker { font-size: 12px; color: var(--color-text-muted); font-weight: 700; letter-spacing: 1px; }
.recap-period { font-size: 24px; font-weight: 900; color: var(--color-text-strong, #794f27); }
.recap-anon {
  width: 44px; height: 44px;
  flex-shrink: 0;
  border-radius: 50%;
  object-fit: cover;
  background: var(--color-surface, #fff);
  border: 2px solid var(--color-border);
}

.recap-caption {
  font-size: 14px;
  line-height: 1.65;
  font-weight: 700;
  color: var(--color-text-strong, #794f27);
  background: var(--color-surface-2, #f0ece2);
  border-radius: 14px;
  border: 1.5px dashed var(--color-border, #c4b89e);
  padding: 12px 14px;
  word-break: break-word;
}

/* KPI：整行 label + value，数字单行右对齐，绝不换行 */
.recap-kpis {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: auto;
}
.kpi-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  background: var(--color-surface, #fff);
  border: 1.5px solid var(--color-border-light, #d4c9b4);
  border-radius: 12px;
  padding: 9px 14px;
}
.kpi-label { font-size: 12px; color: var(--color-text-muted); flex-shrink: 0; }
.kpi-value {
  font-size: 17px;
  font-weight: 900;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.kpi-value.spend, .tile-main.spend { color: var(--color-up, #DC2626); }
.kpi-value.income, .tile-main.income { color: var(--color-down, #15803D); }

.recap-tiles {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}
.recap-card.is-pc .recap-tiles { grid-template-columns: 1fr 1fr; }

.tile {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  background: var(--color-surface, #fff);
  border: 1.5px solid var(--color-border-light, #d4c9b4);
  border-radius: 14px;
  padding: 10px 12px;
}
.tile-ico { font-size: 22px; flex-shrink: 0; }
.tile-body { min-width: 0; flex: 1 1 auto; }
.tile-label { font-size: 11px; color: var(--color-text-muted); }
.tile-main { font-size: 15px; font-weight: 800; color: var(--color-text-strong, #794f27); font-variant-numeric: tabular-nums; word-break: break-word; line-height: 1.3; }
.tile-sub { font-size: 11px; color: var(--color-text-muted); word-break: break-word; line-height: 1.4; }

.recap-foot {
  margin-top: auto;
  padding-top: 6px;
  text-align: center;
  font-size: 11px;
  color: var(--color-text-muted);
}

.recap-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-top: 14px;
}
.recap-tag {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 50px;
  background: var(--color-border);
  color: var(--color-text-muted);
}
</style>
