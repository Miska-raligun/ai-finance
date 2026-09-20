<!-- views/PublicTripView.vue — 公开分享页(/s/:token)
     无需登录,只读。不渲染应用外壳(侧边栏/顶栏),访客看不到也进不去账本等功能。
     数据来自 /api/public/trips/<token>,后端按白名单输出,不含手记与打包清单。 -->
<template>
  <div class="pub" :style="accentVars">
    <div v-if="loading" class="pub-state">加载中…</div>

    <div v-else-if="error" class="pub-state pub-err">
      <div class="pub-err-t">链接无效或已失效</div>
      <p>可能是分享已被取消,或者链接不完整。</p>
    </div>

    <template v-else>
      <header class="pub-hero">
        <div class="pub-wrap">
          <div v-if="trip.code" class="pub-code">{{ trip.code }}</div>
          <h1 class="pub-title">{{ trip.title }}</h1>
          <div v-if="trip.subtitle" class="pub-sub">{{ trip.subtitle }}</div>
          <div class="pub-range">{{ trip.start_date }} — {{ trip.end_date }} · 共 {{ days.length }} 天</div>
        </div>
      </header>

      <main class="pub-wrap pub-main">
        <section v-if="hasAnyStop" class="pub-card">
          <TripMap :days="days" title="全程路线" />
        </section>

        <!-- 速查:只包含行程所有者显式设为公开的条目 -->
        <section v-if="facts.length" class="pub-card">
          <h3 class="pub-sec-t">速查</h3>
          <TripFacts :facts="facts" readonly />
        </section>

        <section
          v-for="d in days"
          :key="d.day_no"
          class="pub-card pub-day"
        >
          <div class="pub-day-head">
            <span class="pub-dayno">Day {{ d.day_no }}</span>
            <span class="pub-date">{{ prettyDate(d.date) }}</span>
          </div>
          <div v-if="d.route" class="pub-route">{{ d.route }}</div>
          <div class="pub-meta">
            <span v-if="d.transport" class="pub-chip">{{ d.transport }}</span>
            <span v-if="d.meal" class="pub-chip">含餐 {{ d.meal }}</span>
          </div>

          <ol v-if="(d.detail.sched || []).length" class="pub-tl">
            <li v-for="(s, i) in d.detail.sched" :key="i">
              <span class="pub-tl-time">{{ s[0] }}</span>
              <span class="pub-tl-body"><b>{{ s[1] }}</b><em v-if="s[2]">{{ s[2] }}</em></span>
            </li>
          </ol>

          <template v-for="g in tipGroups(d)" :key="g.key">
            <div v-if="g.items.length" class="pub-sub-sec">
              <h4>{{ g.label }}</h4>
              <ul><li v-for="(t, i) in g.items" :key="i">{{ t }}</li></ul>
            </div>
          </template>

          <div v-if="d.detail.stay && (d.detail.stay.h || d.detail.stay.a)" class="pub-sub-sec">
            <h4>住宿</h4>
            <div class="pub-stay">
              <b>{{ d.detail.stay.h }}</b>
              <span v-if="d.detail.stay.a">{{ d.detail.stay.a }}</span>
            </div>
          </div>
        </section>
      </main>

      <footer class="pub-foot">这是一份只读的行程分享</footer>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import TripMap from '@/components/TripMap.vue'
import TripFacts from '@/components/TripFacts.vue'

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

const accentVars = computed(() => {
  const a = ACCENTS[trip.value?.accent] || ACCENTS.glacier
  return { '--trip-accent': a.color, '--trip-accent-weak': a.weak, '--trip-accent-ink': a.ink }
})

const hasAnyStop = computed(() => days.value.some(d =>
  (d.detail?.stops || []).some(s => isFinite(Number(s.lat)) && isFinite(Number(s.lng)))))

function tipGroups(d) {
  const x = d.detail || {}
  return [
    { key: 'spots', label: '景点', items: (x.spots || []).map(s => Array.isArray(s) ? (s[1] ? `${s[0]}（${s[1]}）` : s[0]) : String(s)) },
    { key: 'todo', label: '贴士', items: x.todo || [] },
    { key: 'cam', label: '拍摄建议', items: x.cam || [] },
    { key: 'buy', label: '买什么', items: x.buy || [] },
    { key: 'warn', label: '注意', items: x.warn || [] },
  ]
}

function prettyDate(iso) {
  if (!iso) return ''
  const d = new Date(iso + 'T00:00:00')
  const w = ['周日','周一','周二','周三','周四','周五','周六'][d.getDay()]
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日 · ${w}`
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
    if (trip.value.title) document.title = `${trip.value.title} · 行程`
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.pub { min-height: 100dvh; background: var(--color-bg, #f5f3ea); }
.pub-wrap { max-width: 760px; margin: 0 auto; padding: 0 18px; }
.pub-state { padding: 80px 18px; text-align: center; color: var(--color-text-muted); }
.pub-err-t { font-size: 17px; font-weight: 800; color: var(--color-text-strong); margin-bottom: 6px; }

.pub-hero { background: var(--trip-accent-weak); border-bottom: 2px solid var(--trip-accent); padding: 30px 0 24px; }
.pub-code { font-size: 11px; letter-spacing: .1em; color: var(--trip-accent-ink); opacity: .7; }
.pub-title { margin: 4px 0 0; font-size: 26px; font-weight: 900; color: var(--trip-accent-ink); }
.pub-sub { font-size: 14px; color: var(--trip-accent-ink); opacity: .82; margin-top: 3px; }
.pub-range { font-size: 12px; color: var(--trip-accent-ink); opacity: .7; margin-top: 8px; font-variant-numeric: tabular-nums; }

.pub-main { padding-top: 18px; padding-bottom: 28px; display: flex; flex-direction: column; gap: 14px; }
.pub-card {
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border-light, #e3ddd0);
  border-radius: 14px; padding: 14px 16px;
}
.pub-sec-t { margin: 0 0 6px; font-size: 13px; font-weight: 800; color: var(--color-text-strong); }
.pub-day-head { display: flex; align-items: baseline; gap: 10px; }
.pub-dayno {
  font-size: 11px; font-weight: 800; letter-spacing: .06em; color: #fff;
  background: var(--trip-accent); padding: 2px 8px; border-radius: 999px;
}
.pub-date { font-size: 12px; color: var(--color-text-muted); font-variant-numeric: tabular-nums; }
.pub-route { margin-top: 6px; font-size: 17px; font-weight: 800; color: var(--color-text-strong); }
.pub-meta { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }
.pub-chip { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: var(--trip-accent-weak); color: var(--trip-accent-ink); }

.pub-tl { list-style: none; margin: 12px 0 0; padding: 0; }
.pub-tl li { display: flex; gap: 12px; padding: 4px 0; }
.pub-tl-time { width: 46px; flex-shrink: 0; text-align: right; font-size: 12px; color: var(--color-text-muted); font-variant-numeric: tabular-nums; }
.pub-tl-body { font-size: 13px; line-height: 1.5; }
.pub-tl-body b { font-weight: 700; }
.pub-tl-body em { display: block; font-style: normal; font-size: 12px; color: var(--color-text-muted); }

.pub-sub-sec { margin-top: 12px; }
.pub-sub-sec h4 { margin: 0 0 4px; font-size: 11px; font-weight: 800; letter-spacing: .08em; color: var(--color-text-muted); }
.pub-sub-sec ul { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.7; }
.pub-stay { font-size: 13px; display: flex; flex-direction: column; }
.pub-stay span { color: var(--color-text-muted); font-size: 12px; }

.pub-foot { text-align: center; padding: 18px; font-size: 11px; color: var(--color-text-muted); }

@media (max-width: 768px) {
  .pub-title { font-size: 21px; }
  .pub-hero { padding: 22px 0 18px; }
}
</style>
