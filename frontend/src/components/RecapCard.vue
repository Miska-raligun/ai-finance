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
      <!-- 导出范围：内层固定宽度容器，按钮在容器外不进图 -->
      <div ref="cardRef" class="recap-card">
        <div class="recap-deco" aria-hidden="true"></div>

        <header class="recap-head">
          <div class="recap-title">
            <span class="recap-emoji">🐾</span>
            <div>
              <div class="recap-kicker">本月回顾</div>
              <div class="recap-period">{{ recap.period }}</div>
            </div>
          </div>
          <img src="/favicon.ico" class="recap-anon" alt="Anon" />
        </header>

        <div class="recap-caption">{{ recap.caption }}</div>

        <div class="recap-kpis">
          <div class="kpi">
            <div class="kpi-label">总支出</div>
            <div class="kpi-value spend">¥{{ fmt(recap.spend_total) }}</div>
          </div>
          <div class="kpi">
            <div class="kpi-label">总收入</div>
            <div class="kpi-value income">¥{{ fmt(recap.income_total) }}</div>
          </div>
          <div class="kpi">
            <div class="kpi-label">净结余</div>
            <div class="kpi-value" :class="recap.net >= 0 ? 'income' : 'spend'">
              {{ recap.net >= 0 ? '+' : '-' }}¥{{ fmt(Math.abs(recap.net)) }}
            </div>
          </div>
        </div>

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

        <footer class="recap-foot">
          由 Anon 生成 · 数据来自你本月的真实记账 🌿
        </footer>
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
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { toPng } from 'html-to-image'
import EmptyHint from '@/components/EmptyHint.vue'

const props = defineProps({
  recap: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})

const cardRef = ref(null)
const exporting = ref(false)

function fmt(n) {
  if (n == null) return '0.00'
  return Number(n).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function exportPng() {
  if (!cardRef.value) return
  exporting.value = true
  try {
    // 读取当前主题底色，避免导出图背景透明 / 发黑
    const bg = getComputedStyle(document.body).getPropertyValue('--color-surface').trim() || '#f7f3df'
    const dataUrl = await toPng(cardRef.value, {
      pixelRatio: 2,
      backgroundColor: bg,
      cacheBust: true,
    })
    const a = document.createElement('a')
    a.href = dataUrl
    a.download = `回顾_${props.recap?.period || ''}.png`
    a.click()
  } catch (e) {
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
  max-width: 460px;
  margin: 0 auto;
  padding: 22px 22px 16px;
  border-radius: var(--radius-card, 20px);
  background:
    radial-gradient(120% 80% at 100% 0%, var(--color-primary-light, #e6f9f6) 0%, transparent 55%),
    var(--color-surface, #f7f3df);
  border: 2px solid var(--color-border, #c4b89e);
  box-shadow: var(--shadow-card, 0 4px 10px rgba(107,92,67,0.18));
}
.recap-deco {
  position: absolute;
  right: -30px;
  bottom: -30px;
  width: 130px;
  height: 130px;
  border-radius: 50%;
  background: var(--color-primary-light, #e6f9f6);
  opacity: 0.5;
  pointer-events: none;
}

.recap-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  position: relative;
  z-index: 1;
}
.recap-title { display: flex; align-items: center; gap: 10px; }
.recap-emoji { font-size: 30px; }
.recap-kicker { font-size: 12px; color: var(--color-text-muted); font-weight: 700; letter-spacing: 1px; }
.recap-period { font-size: 22px; font-weight: 900; color: var(--color-text-strong, #794f27); }
.recap-anon { width: 40px; height: 40px; border-radius: 50%; border: 2px solid var(--color-border); }

.recap-caption {
  position: relative;
  z-index: 1;
  margin: 14px 0 16px;
  padding: 12px 14px;
  font-size: 14px;
  line-height: 1.6;
  font-weight: 700;
  color: var(--color-text-strong, #794f27);
  background: var(--color-surface-2, #f0ece2);
  border-radius: 14px;
  border: 1.5px dashed var(--color-border, #c4b89e);
}

.recap-kpis {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-bottom: 12px;
}
.kpi {
  background: var(--color-surface, #fff);
  border: 1.5px solid var(--color-border-light, #d4c9b4);
  border-radius: 14px;
  padding: 10px 8px;
  text-align: center;
}
.kpi-label { font-size: 11px; color: var(--color-text-muted); margin-bottom: 3px; }
.kpi-value { font-size: clamp(13px, 4vw, 17px); font-weight: 900; word-break: break-all; }
.kpi-value.spend, .tile-main.spend { color: var(--color-up, #DC2626); }
.kpi-value.income, .tile-main.income { color: var(--color-down, #15803D); }

.recap-tiles {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}
.tile {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--color-surface, #fff);
  border: 1.5px solid var(--color-border-light, #d4c9b4);
  border-radius: 14px;
  padding: 10px 12px;
}
.tile-ico { font-size: 22px; flex-shrink: 0; }
.tile-body { min-width: 0; }
.tile-label { font-size: 11px; color: var(--color-text-muted); }
.tile-main { font-size: 15px; font-weight: 800; color: var(--color-text-strong, #794f27); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tile-sub { font-size: 11px; color: var(--color-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.recap-foot {
  position: relative;
  z-index: 1;
  margin-top: 14px;
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

@media (max-width: 768px) {
  .recap-tiles { grid-template-columns: 1fr; }
}
</style>
