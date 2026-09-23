<!-- components/TripSpending.vue — 这趟花了多少:账本里 trip_id 指向本行程的条目

     这是「旅行计划」留在记账 App 里的理由。归属存在 records.trip_id 上,
     不按日期现算——出发前买的机票、回来才结的账、旅行途中在家扣的订阅费,
     光看日期全都会算错。
-->
<template>
  <div class="sp">
    <div v-if="loading" class="sp-empty">正在算…</div>

    <template v-else>
      <div class="sp-cards">
        <div class="sp-card">
          <span class="sp-k">总支出</span>
          <b class="sp-v">{{ money(data.total) }}</b>
        </div>
        <div v-if="data.refund" class="sp-card">
          <span class="sp-k">退税 / 退款</span>
          <b class="sp-v back">-{{ money(data.refund) }}</b>
        </div>
        <div class="sp-card wide">
          <span class="sp-k">净花费</span>
          <b class="sp-v big">{{ money(data.net) }}</b>
          <span v-if="perDay" class="sp-sub">每天约 {{ money(perDay) }}</span>
        </div>
      </div>

      <div v-if="!data.count" class="sp-empty">
        <p>这趟还没有关联的账。</p>
        <p class="sp-hint">
          行程期间新记的账会自动归到这趟。已经记过的,可以按日期一次归入。
        </p>
      </div>

      <template v-else>
        <div v-if="data.by_category.length" class="sp-block">
          <h4 class="sp-h">花在哪</h4>
          <div v-for="c in data.by_category" :key="c.category" class="sp-row">
            <span class="sp-row-k">{{ c.category }}</span>
            <span class="sp-bar"><i :style="{ width: pct(c.amount, maxCat) + '%' }" /></span>
            <span class="sp-row-v">{{ money(c.amount) }}</span>
          </div>
        </div>

        <div v-if="data.by_day.length" class="sp-block">
          <h4 class="sp-h">每天</h4>
          <div v-for="d in data.by_day" :key="d.date" class="sp-row">
            <span class="sp-row-k mono">{{ dayLabel(d.date) }}</span>
            <span class="sp-bar"><i :style="{ width: pct(d.amount, maxDay) + '%' }" /></span>
            <span class="sp-row-v">{{ money(d.amount) }}</span>
          </div>
        </div>

        <div class="sp-block">
          <h4 class="sp-h">
            明细
            <button type="button" class="sp-b ghost" @click="showList = !showList">
              {{ showList ? '收起' : `展开 ${data.count} 条` }}
            </button>
          </h4>
          <ul v-if="showList" class="sp-list">
            <li v-for="it in entries" :key="it.kind + it.id" class="sp-item">
              <span class="sp-i-date mono">{{ it.date?.slice(5) }}</span>
              <span class="sp-i-cat" :class="{ back: it.kind === 'in' }">{{ it.category }}</span>
              <span class="sp-i-note">{{ it.note }}</span>
              <span class="sp-i-amt" :class="{ back: it.kind === 'in' }">
                {{ it.kind === 'in' ? '-' : '' }}{{ money(it.amount) }}
              </span>
              <button
                type="button"
                class="sp-x"
                title="不属于这趟"
                :disabled="busy"
                @click="detachOne(it)"
              >✕</button>
            </li>
          </ul>
        </div>
      </template>

      <div class="sp-acts">
        <button type="button" class="sp-b" :disabled="busy" @click="attach">
          按日期归入({{ trip.start_date }} ~ {{ trip.end_date }})
        </button>
        <button
          v-if="data.count"
          type="button"
          class="sp-b ghost"
          :disabled="busy"
          @click="detachAll"
        >全部解除</button>
      </div>
      <p class="sp-hint">
        「按日期归入」只会认领<b>还没归属</b>的条目,不会从别的行程里抢。
      </p>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'

const props = defineProps({
  trip: { type: Object, required: true },
})

const loading = ref(true)
const busy = ref(false)
const showList = ref(false)
const data = ref({ total: 0, refund: 0, net: 0, count: 0, by_category: [], by_day: [], records: [], income: [] })

const maxCat = computed(() => Math.max(1, ...data.value.by_category.map(c => c.amount)))
const maxDay = computed(() => Math.max(1, ...data.value.by_day.map(d => d.amount)))

/** 明细按日期混排:支出和退款挨在一起看才知道某天净掏了多少。 */
const entries = computed(() => [
  ...data.value.records.map(r => ({ ...r, kind: 'out' })),
  ...data.value.income.map(r => ({ ...r, kind: 'in' })),
].sort((a, b) => (a.date || '').localeCompare(b.date || '') || a.id - b.id))

const perDay = computed(() => {
  const n = data.value.by_day.length
  return n > 1 ? Math.round(data.value.net / n) : 0
})

function money(n) {
  return '¥' + Number(n || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
function pct(v, max) {
  return Math.max(2, Math.round((v / max) * 100))
}
function dayLabel(date) {
  // 行程里说"第几天"比说日期好认
  const start = props.trip.start_date
  if (!start) return date.slice(5)
  const d = Math.round((Date.parse(date) - Date.parse(start)) / 86400000) + 1
  return d >= 1 ? `D${d}` : date.slice(5)
}

async function load() {
  loading.value = true
  try {
    const { data: d } = await api.get(`/api/trips/${props.trip.id}/spending`)
    data.value = d
  } catch { /* 拦截器已提示 */ } finally {
    loading.value = false
  }
}

async function attach() {
  busy.value = true
  try {
    const { data: d } = await api.post(`/api/trips/${props.trip.id}/spending/attach`, {})
    ElMessage.success(d.moved ? `归入 ${d.moved} 条` : '这段时间没有待归属的账')
    if (d.moved) await load()
  } catch { /* 同上 */ } finally {
    busy.value = false
  }
}

async function detachAll() {
  try {
    await ElMessageBox.confirm(
      '把这趟的账全部解除归属?账目本身不会删,只是不再算进这趟。',
      '解除归属',
      { confirmButtonText: '解除', cancelButtonText: '再想想' },
    )
  } catch { return }
  busy.value = true
  try {
    await api.delete(`/api/trips/${props.trip.id}/spending/attach`)
    await load()
  } catch { /* 同上 */ } finally {
    busy.value = false
  }
}

async function detachOne(it) {
  busy.value = true
  const url = it.kind === 'in' ? `/api/income/${it.id}` : `/api/records/${it.id}`
  try {
    // PUT 是整条覆盖,原样回填其余字段,只把 trip_id 清掉
    await api.put(url, {
      category: it.category, amount: it.amount, note: it.note || '',
      date: it.date, trip_id: null,
    })
    await load()
  } catch { /* 同上 */ } finally {
    busy.value = false
  }
}

watch(() => props.trip.id, load)
onMounted(load)
</script>

<style scoped>
.sp-cards { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
.sp-card {
  flex: 1 1 120px; min-width: 110px; padding: 10px 12px; border-radius: 12px;
  background: var(--trip-accent-weak, var(--color-surface-2, rgba(0,0,0,.04)));
  display: flex; flex-direction: column; gap: 2px;
}
.sp-card.wide { flex: 2 1 180px; }
.sp-k { font-size: 11.5px; color: var(--color-text-muted); }
.sp-v { font-size: 18px; font-weight: 800; font-variant-numeric: tabular-nums; }
.sp-v.big { font-size: 24px; color: var(--trip-accent, var(--color-primary)); }
.sp-v.back { color: var(--color-success, #3a8f5a); }
.sp-sub { font-size: 11.5px; color: var(--color-text-muted); font-variant-numeric: tabular-nums; }

.sp-block { margin-bottom: 16px; }
.sp-h {
  display: flex; align-items: center; gap: 10px;
  margin: 0 0 8px; font-size: 13px; font-weight: 700;
}
.sp-row { display: flex; align-items: center; gap: 8px; padding: 3px 0; font-size: 12.5px; }
.sp-row-k { flex: 0 0 5.5em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sp-row-v { flex: 0 0 auto; font-variant-numeric: tabular-nums; color: var(--color-text-muted); }
.sp-bar { flex: 1; height: 7px; border-radius: 999px; background: var(--color-surface-2, rgba(0,0,0,.07)); overflow: hidden; }
.sp-bar i { display: block; height: 100%; background: var(--trip-accent, var(--color-primary)); }
.mono { font-variant-numeric: tabular-nums; }

.sp-list { list-style: none; margin: 0; padding: 0; }
.sp-item {
  display: flex; align-items: baseline; gap: 8px; padding: 5px 0; font-size: 12.5px;
  border-bottom: 1px solid var(--color-border, rgba(0,0,0,.06));
}
.sp-i-date { flex: 0 0 3em; color: var(--color-text-muted); }
.sp-i-cat { flex: 0 0 auto; font-weight: 600; }
.sp-i-cat.back, .sp-i-amt.back { color: var(--color-success, #3a8f5a); }
.sp-i-note { flex: 1; color: var(--color-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sp-i-amt { flex: 0 0 auto; font-variant-numeric: tabular-nums; font-weight: 700; }
.sp-x {
  appearance: none; border: 0; background: none; cursor: pointer; padding: 0 2px;
  color: var(--color-text-muted); font-size: 12px; line-height: 1;
}
.sp-x:disabled { opacity: .4; cursor: default; }

.sp-acts { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px; }
.sp-b {
  appearance: none; border: 1px solid var(--trip-accent, var(--color-primary));
  background: var(--trip-accent, var(--color-primary)); color: #fff;
  font: inherit; font-size: 12px; font-weight: 700;
  padding: 4px 14px; border-radius: 999px; cursor: pointer;
}
.sp-b.ghost { background: var(--color-surface); color: var(--trip-accent, var(--color-primary)); font-weight: 400; }
.sp-b:disabled { opacity: .55; cursor: default; }
.sp-empty { padding: 18px 0; color: var(--color-text-muted); font-size: 13px; }
.sp-empty p { margin: 0 0 6px; }
.sp-hint { font-size: 11.5px; color: var(--color-text-muted); margin: 8px 0 0; line-height: 1.6; }
</style>
