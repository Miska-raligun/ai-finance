<!-- views/PublicTripView.vue — 公开分享页(/s/:token)
     无需登录,只读。不渲染应用外壳(侧边栏/顶栏),访客看不到也进不去账本等功能。
     数据来自 /api/public/trips/<token>,后端按白名单输出,不含手记与打包清单。 -->
<template>
  <div class="pub" :style="accentVars">
    <div v-if="loading" class="pub-state">
      <div class="pub-spin" />
      <span>正在打开行程…</span>
    </div>

    <div v-else-if="error" class="pub-state pub-err">
      <div class="pub-err-mark">🧭</div>
      <div class="pub-err-t">链接无效或已失效</div>
      <p>可能是分享已被取消,或者链接不完整。</p>
    </div>

    <template v-else>
      <!-- 头图:满宽主题色带 -->
      <header class="hero">
        <div class="hero-in">
          <div v-if="trip.code" class="hero-code">{{ trip.code }}</div>
          <h1 class="hero-t">{{ trip.title }}</h1>
          <div v-if="trip.subtitle" class="hero-sub">{{ trip.subtitle }}</div>
          <p v-if="trip.cover_note" class="hero-note">{{ trip.cover_note }}</p>

          <div class="hero-stats">
            <div class="stat">
              <b>{{ days.length }}</b><span>天</span>
            </div>
            <div v-if="stopCount" class="stat">
              <b>{{ stopCount }}</b><span>个地点</span>
            </div>
            <div class="stat stat-wide">
              <b>{{ shortDate(trip.start_date) }} – {{ shortDate(trip.end_date) }}</b><span>行程日期</span>
            </div>
          </div>
        </div>
      </header>

      <!-- 天数导航:点一下跳到那天,滚动时高亮当前天 -->
      <nav v-if="days.length > 1" class="daybar" aria-label="按天跳转">
        <div class="daybar-in">
          <button
            v-for="d in days"
            :key="d.day_no"
            type="button"
            class="daybar-chip"
            :class="{ on: activeDay === d.day_no }"
            @click="jump(d.day_no)"
          >
            <b>D{{ d.day_no }}</b>
            <span>{{ shortDate(d.date) }}</span>
          </button>
        </div>
      </nav>

      <div class="pub-wrap">
        <!-- 地图:整个分享页的视觉主角,给满宽 -->
        <section v-if="hasAnyStop" class="card map-card">
          <TripMap :days="days" title="全程路线" />
        </section>

        <div class="cols" :class="{ solo: !facts.length }">
          <main class="col-main">
            <ol class="dlist">
              <li
                v-for="d in days"
                :key="d.day_no"
                :id="`day-${d.day_no}`"
                ref="dayEls"
                :data-day="d.day_no"
                class="day"
                :class="{ blank: isBlank(d) }"
              >
                <div class="day-rail"><span class="day-no">{{ d.day_no }}</span></div>

                <div class="card day-card">
                  <div class="day-top">
                    <h3 class="day-route">{{ d.route || '自由活动' }}</h3>
                    <span class="day-date">{{ prettyDate(d.date) }}</span>
                  </div>

                  <div v-if="d.transport || d.meal" class="chips">
                    <span v-if="d.transport" class="chip">{{ d.transport }}</span>
                    <span v-if="d.meal" class="chip chip-ghost">含餐 {{ d.meal }}</span>
                  </div>

                  <ol v-if="schedOf(d).length" class="sched">
                    <li v-for="(s, i) in schedOf(d)" :key="i" :class="{ hi: s[3] }">
                      <span class="sched-time">{{ s[0] }}</span>
                      <span class="sched-body"><b>{{ s[1] }}</b><em v-if="s[2]">{{ s[2] }}</em></span>
                    </li>
                  </ol>

                  <!-- 贴士类分栏排:宽屏两列,少一半空白 -->
                  <div v-if="tipGroups(d).length" class="tipgrid">
                    <section v-for="g in tipGroups(d)" :key="g.key" class="tip">
                      <h4>{{ g.label }}</h4>
                      <ul><li v-for="(t, i) in g.items" :key="i">{{ t }}</li></ul>
                    </section>
                  </div>

                  <div v-if="stayOf(d)" class="stay">
                    <div class="stay-txt">
                      <b>🏨 {{ stayOf(d).h }}</b>
                      <span v-if="stayOf(d).a">{{ stayOf(d).a }}</span>
                    </div>
                    <!-- 外链系统地图:不嵌第三方地图,不给外部服务发坐标 -->
                    <a
                      v-if="stayMap(d)"
                      class="maplink"
                      :href="stayMap(d)"
                      target="_blank"
                      rel="noopener noreferrer"
                    >📍 地图</a>
                  </div>
                </div>
              </li>
            </ol>
          </main>

          <!-- 速查:只包含行程所有者显式设为公开的条目 -->
          <aside v-if="facts.length" class="col-aside">
            <!-- 窄屏折叠：速查排在每日安排之前(应急电话不该埋在最底下),
                 但 9 条展开会把行程顶到三屏以外,所以默认收起、点一下展开。 -->
            <details class="card aside-card" :open="wide">
              <summary class="aside-t">速查<span class="aside-n">{{ facts.length }} 条</span></summary>
              <TripFacts :facts="facts" readonly />
            </details>
          </aside>
        </div>
      </div>

      <footer class="pub-foot">
        <span>只读行程分享 · 手记与账本不在其中</span>
      </footer>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import TripMap from '@/components/TripMap.vue'
import TripFacts from '@/components/TripFacts.vue'
import { mapUrl } from '@/utils/maplink'

const ACCENTS = {
  glacier: { color: '#2B6A80', weak: '#D9E6EB', ink: '#17414f' },
  aurora:  { color: '#3C8C6E', weak: '#D8EBE2', ink: '#215240' },
  ember:   { color: '#9A5A2C', weak: '#F3E6D8', ink: '#5e3418' },
  sakura:  { color: '#B4576F', weak: '#F6E1E6', ink: '#6d2f3f' },
  desert:  { color: '#A8843C', weak: '#F2E9D4', ink: '#5f4a1c' },
  violet:  { color: '#6A5A9A', weak: '#E5E1F1', ink: '#3d3363' },
}

const route = useRoute()
const trip = ref({})
const days = ref([])
const facts = ref([])
const loading = ref(true)
const error = ref(false)
const dayEls = ref([])
// 宽屏侧栏常驻展开,窄屏折叠(见模板里的 <details>)
const WIDE_MQ = '(min-width: 961px)'
const wide = ref(typeof window !== 'undefined' && window.matchMedia(WIDE_MQ).matches)
let mql = null
const activeDay = ref(0)
let observer = null

const accentVars = computed(() => {
  const a = ACCENTS[trip.value?.accent] || ACCENTS.glacier
  return { '--trip-accent': a.color, '--trip-accent-weak': a.weak, '--trip-accent-ink': a.ink }
})

function coords(d) {
  return (d.detail?.stops || []).filter(s => isFinite(Number(s.lat)) && isFinite(Number(s.lng)))
}
const hasAnyStop = computed(() => days.value.some(d => coords(d).length))
const stopCount = computed(() => days.value.reduce((n, d) => n + coords(d).length, 0))

function schedOf(d) { return d.detail?.sched || [] }
function stayOf(d) {
  const s = d.detail?.stay
  return s && (s.h || s.a) ? s : null
}
function stayMap(d) {
  const s = stayOf(d)
  return s ? mapUrl({ lat: s.lat, lng: s.lng, name: s.h, addr: s.a }) : ''
}

function tipGroups(d) {
  const x = d.detail || {}
  return [
    { key: 'spots', label: '景点', items: (x.spots || []).map(s => Array.isArray(s) ? (s[1] ? `${s[0]}（${s[1]}）` : s[0]) : String(s)) },
    { key: 'todo', label: '贴士', items: x.todo || [] },
    { key: 'cam', label: '拍摄建议', items: x.cam || [] },
    { key: 'buy', label: '买什么', items: x.buy || [] },
    { key: 'warn', label: '注意', items: x.warn || [] },
  ].filter(g => g.items.length)
}

/** 没有任何内容的一天:渲染成一行提示,而不是一张空卡片(原来大片留白就是这么来的)。 */
function isBlank(d) {
  return !schedOf(d).length && !tipGroups(d).length && !stayOf(d)
}

function prettyDate(iso) {
  if (!iso) return ''
  const d = new Date(iso + 'T00:00:00')
  const w = ['周日','周一','周二','周三','周四','周五','周六'][d.getDay()]
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日 · ${w}`
}
function shortDate(iso) {
  if (!iso) return ''
  const [, m, d] = iso.split('-')
  return `${Number(m)}/${Number(d)}`
}

function jump(dayNo) {
  document.getElementById(`day-${dayNo}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  activeDay.value = dayNo
}

/** 滚动时高亮当前天。用 IntersectionObserver 而不是 scroll 事件,省掉每帧计算。 */
function observeDays() {
  observer?.disconnect()
  if (!dayEls.value?.length) return
  observer = new IntersectionObserver((entries) => {
    const vis = entries.filter(e => e.isIntersecting)
      .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0]
    if (vis) activeDay.value = Number(vis.target.dataset.day)
  }, { rootMargin: '-96px 0px -60% 0px' })
  dayEls.value.forEach(el => el && observer.observe(el))
}

onMounted(async () => {
  // 故意用原生 fetch:不经过 axios 拦截器,匿名 401/错误不会触发跳登录
  try {
    const res = await fetch(`/api/public/trips/${encodeURIComponent(route.params.token)}`)
    if (!res.ok) { error.value = true; return }
    const data = await res.json()
    trip.value = data.trip || {}
    days.value = data.days || []
    facts.value = data.facts || []
    activeDay.value = days.value[0]?.day_no || 0
    if (trip.value.title) document.title = `${trip.value.title} · 行程`
    await nextTick()
    observeDays()
    mql = window.matchMedia(WIDE_MQ)
    mql.addEventListener('change', onMq)
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
})

function onMq(e) { wide.value = e.matches }

onBeforeUnmount(() => {
  observer?.disconnect()
  mql?.removeEventListener('change', onMq)
})
</script>

<style scoped>
.pub {
  min-height: 100dvh;
  background:
    radial-gradient(1100px 420px at 50% -220px, var(--trip-accent-weak), transparent 70%),
    var(--color-bg, #f5f3ea);
}
.pub-wrap { max-width: 1120px; margin: 0 auto; padding: 18px 18px 30px; }

/* 状态页 */
.pub-state {
  display: flex; flex-direction: column; align-items: center; gap: 10px;
  padding: 110px 18px; text-align: center; color: var(--color-text-muted); font-size: 13px;
}
.pub-spin {
  width: 22px; height: 22px; border-radius: 50%;
  border: 2px solid var(--color-border-light); border-top-color: var(--trip-accent);
  animation: pub-rot .8s linear infinite;
}
@keyframes pub-rot { to { transform: rotate(360deg); } }
.pub-err-mark { font-size: 32px; }
.pub-err-t { font-size: 17px; font-weight: 800; color: var(--color-text-strong); }
.pub-err p { margin: 0; }

/* 头图 */
.hero {
  background: linear-gradient(140deg, var(--trip-accent-weak) 0%, var(--color-surface, #fff) 130%);
  border-bottom: 1px solid var(--trip-accent);
  box-shadow: inset 0 -3px 0 0 var(--trip-accent);
}
.hero-in { max-width: 1120px; margin: 0 auto; padding: 34px 18px 26px; }
.hero-code {
  display: inline-block; font-size: 11px; letter-spacing: .12em; font-weight: 700;
  color: var(--trip-accent-ink); background: rgba(255,255,255,.55);
  border: 1px solid var(--trip-accent); border-radius: 999px; padding: 2px 10px;
}
.hero-t {
  margin: 10px 0 0; font-size: 32px; line-height: 1.15; font-weight: 900;
  letter-spacing: -.01em; color: var(--trip-accent-ink);
}
.hero-sub { margin-top: 5px; font-size: 15px; color: var(--trip-accent-ink); opacity: .82; }
.hero-note {
  margin: 12px 0 0; padding-left: 10px; max-width: 58ch;
  border-left: 3px solid var(--trip-accent); font-size: 13px; line-height: 1.7;
  color: var(--trip-accent-ink); opacity: .8;
}
.hero-stats { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }
.stat {
  background: rgba(255,255,255,.62); border: 1px solid var(--trip-accent);
  border-radius: 12px; padding: 7px 14px; min-width: 76px;
  display: flex; flex-direction: column; gap: 1px;
}
.stat b {
  font-size: 19px; font-weight: 900; color: var(--trip-accent);
  font-variant-numeric: tabular-nums; line-height: 1.1;
}
.stat span { font-size: 11px; color: var(--trip-accent-ink); opacity: .72; }
.stat-wide b { font-size: 15px; padding-top: 3px; }

/* 天数导航条 */
.daybar {
  position: sticky; top: 0; z-index: 6;
  background: color-mix(in srgb, var(--color-bg, #f5f3ea) 86%, transparent);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--color-border-light, #e3ddd0);
}
.daybar-in {
  max-width: 1120px; margin: 0 auto; padding: 8px 18px;
  display: flex; gap: 6px; overflow-x: auto; scrollbar-width: none;
}
.daybar-in::-webkit-scrollbar { display: none; }
.daybar-chip {
  appearance: none; flex-shrink: 0; cursor: pointer; font: inherit;
  display: flex; flex-direction: column; align-items: center; line-height: 1.25;
  border: 1px solid var(--color-border-light, #e3ddd0); background: var(--color-surface, #fff);
  border-radius: 10px; padding: 4px 11px; color: var(--color-text-muted);
}
.daybar-chip b { font-size: 12px; font-weight: 800; }
.daybar-chip span { font-size: 10px; opacity: .8; font-variant-numeric: tabular-nums; }
.daybar-chip:hover { border-color: var(--trip-accent); color: var(--trip-accent-ink); }
.daybar-chip.on {
  background: var(--trip-accent); border-color: var(--trip-accent); color: #fff;
}

/* 卡片与分栏 */
.card {
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border-light, #e3ddd0);
  border-radius: 14px; padding: 14px 16px;
}
.map-card { margin-bottom: 16px; }
/* 地图按 760×380 的 viewBox 等比放大，满宽时会有 540px 高，几乎吃掉整屏。
   压到半屏以内，头图、地图、第一天能同屏看到。 */
.map-card :deep(.tmap-svg) { max-height: min(46vh, 420px); }

.cols { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 16px; align-items: start; }
.cols.solo { grid-template-columns: minmax(0, 1fr); }
.col-aside { position: sticky; top: 60px; }
/* 速查比一屏长时卡片内部滚动,底部压一层渐隐,免得文字被硬切一半像渲染坏了 */
.col-aside::after {
  content: ''; position: absolute; left: 1px; right: 1px; bottom: 1px; height: 26px;
  border-radius: 0 0 13px 13px; pointer-events: none;
  background: linear-gradient(transparent, var(--color-surface, #fff));
}
.aside-card { max-height: calc(100dvh - 86px); overflow-y: auto; }
.aside-t {
  margin: 0; font-size: 13px; font-weight: 800; color: var(--color-text-strong);
  list-style: none; cursor: default;
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}
.aside-t::-webkit-details-marker { display: none; }
.aside-n { font-size: 11px; font-weight: 600; color: var(--color-text-muted); }
.aside-card[open] > .aside-t { margin-bottom: 8px; }

/* 按天的时间轴 */
.dlist { list-style: none; margin: 0; padding: 0; position: relative; }
.dlist::before {
  content: ''; position: absolute; left: 13px; top: 12px; bottom: 12px; width: 2px;
  background: linear-gradient(var(--trip-accent), var(--color-border-light, #e3ddd0));
  opacity: .35;
}
.day { display: grid; grid-template-columns: 28px minmax(0, 1fr); gap: 12px; scroll-margin-top: 62px; }
.day + .day { margin-top: 12px; }
.day-rail { display: flex; justify-content: center; padding-top: 12px; }
.day-no {
  width: 28px; height: 28px; border-radius: 50%; flex-shrink: 0;
  display: grid; place-items: center;
  background: var(--trip-accent); color: #fff;
  font-size: 12px; font-weight: 900; font-variant-numeric: tabular-nums;
  box-shadow: 0 0 0 3px var(--color-bg, #f5f3ea);
}
.day-card { min-width: 0; }
.day-top { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.day-route { margin: 0; font-size: 17px; font-weight: 800; color: var(--color-text-strong); }
.day-date { font-size: 12px; color: var(--color-text-muted); font-variant-numeric: tabular-nums; }
.chips { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 7px; }
.chip {
  font-size: 11px; padding: 2px 9px; border-radius: 999px;
  background: var(--trip-accent-weak); color: var(--trip-accent-ink);
}
.chip-ghost { background: transparent; border: 1px solid var(--color-border-light, #e3ddd0); color: var(--color-text-muted); }

.sched { list-style: none; margin: 12px 0 0; padding: 0; position: relative; }
.sched::before {
  content: ''; position: absolute; left: 50px; top: 6px; bottom: 6px; width: 1px;
  background: var(--color-border-light, #e3ddd0);
}
.sched li { display: flex; gap: 13px; padding: 4px 0; }
.sched-time {
  width: 46px; flex-shrink: 0; text-align: right; padding-top: 1px;
  font-size: 12px; color: var(--color-text-muted); font-variant-numeric: tabular-nums;
}
.sched-body { position: relative; padding-left: 12px; font-size: 13px; line-height: 1.55; }
.sched-body::before {
  content: ''; position: absolute; left: -3.5px; top: 6px; width: 7px; height: 7px;
  border-radius: 50%; background: var(--color-border-light, #e3ddd0);
  box-shadow: 0 0 0 2px var(--color-surface, #fff);
}
.sched li.hi .sched-body::before { background: var(--trip-accent); }
.sched-body b { font-weight: 700; }
.sched-body em { display: block; font-style: normal; font-size: 12px; color: var(--color-text-muted); }

.tipgrid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 18px; margin-top: 14px; }
.tip h4 {
  margin: 0 0 3px; font-size: 11px; font-weight: 800; letter-spacing: .08em;
  color: var(--trip-accent); text-transform: none;
}
.tip ul { margin: 0; padding-left: 16px; font-size: 12.5px; line-height: 1.65; }

.stay {
  margin-top: 14px; padding-top: 10px; border-top: 1px dashed var(--color-border-light, #e3ddd0);
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
}
.stay-txt { display: flex; flex-direction: column; min-width: 0; font-size: 13px; }
.stay-txt span { font-size: 12px; color: var(--color-text-muted); }
.maplink {
  flex-shrink: 0; font-size: 12px; font-weight: 700; text-decoration: none;
  color: var(--trip-accent); border: 1px solid var(--trip-accent);
  border-radius: 999px; padding: 3px 11px; line-height: 1.5;
}
.maplink:hover { background: var(--trip-accent); color: #fff; }
/* 没填内容的一天压成一行：14 天的行程里常有一半还没排，
   整张空卡片叠下来就是大片留白。 */
.day.blank + .day.blank { margin-top: 6px; }
.day.blank .day-card { padding: 8px 14px; }
.day.blank .day-rail { padding-top: 7px; }
.day.blank .day-no { background: var(--color-border-light, #e3ddd0); color: var(--color-text-muted); }
.day.blank .day-route { font-size: 14px; font-weight: 700; color: var(--color-text-muted); }

.pub-foot {
  text-align: center; padding: 22px 18px 30px;
  font-size: 11px; color: var(--color-text-muted);
}

@media (max-width: 960px) {
  .cols { grid-template-columns: minmax(0, 1fr); }
  .col-aside { position: static; order: -1; }
  .col-aside::after { display: none; }
  .aside-card { max-height: none; }
  /* 折叠态给个明显的可点提示 */
  .aside-t { cursor: pointer; }
  .aside-n::after { content: ' ▾'; }
  .aside-card[open] .aside-n::after { content: ' ▴'; }
}
@media (max-width: 768px) {
  .hero-in { padding: 24px 16px 20px; }
  .hero-t { font-size: 24px; }
  .hero-sub { font-size: 13.5px; }
  .hero-stats { gap: 8px; margin-top: 14px; }
  .stat { padding: 6px 11px; min-width: 64px; }
  .stat b { font-size: 16px; }
  .pub-wrap { padding: 14px 12px 24px; }
  .card { padding: 12px 13px; border-radius: 12px; }
  .day { grid-template-columns: 22px minmax(0, 1fr); gap: 9px; }
  .dlist::before { left: 10px; }
  .day-no { width: 22px; height: 22px; font-size: 11px; }
  .day-rail { padding-top: 11px; }
  .day-route { font-size: 15.5px; }
  .tipgrid { grid-template-columns: minmax(0, 1fr); gap: 10px; }
}
</style>
