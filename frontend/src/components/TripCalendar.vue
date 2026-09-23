<!-- components/TripCalendar.vue — 行程日历:按月网格铺开,行程内的日子显示当天概览 -->
<template>
  <div class="cal">
    <div class="cal-span">{{ spanLabel }}</div>

    <div class="cal-grid" role="grid">
      <div v-for="w in WEEK" :key="w" class="cal-wd" role="columnheader">{{ w }}</div>

      <button
        v-for="cell in cells"
        :key="cell.iso"
        class="cal-cell"
        :class="{
          'in-trip': !!cell.day,
          'is-outside': !cell.day,
          'is-selected': cell.day && cell.day.day_no === selectedDayNo,
          'is-today': cell.iso === todayIso,
        }"
        :disabled="!cell.day"
        :aria-selected="!!(cell.day && cell.day.day_no === selectedDayNo)"
        role="gridcell"
        @click="cell.day && $emit('select', cell.day.day_no)"
      >
        <span class="cal-date">
          <b v-if="cell.dom === 1" class="cal-mon">{{ cell.month }}月</b>{{ cell.dom }}
        </span>
        <template v-if="cell.day">
          <span class="cal-dayno">D{{ cell.day.day_no }}</span>
          <span class="cal-route">{{ shortRoute(cell.day) }}</span>
          <span v-if="transportIcon(cell.day)" class="cal-icon" :title="cell.day.transport">
            {{ transportIcon(cell.day) }}
          </span>
          <span v-if="cell.day.journal" class="cal-flag" title="已有手记">✎</span>
        </template>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  trip: { type: Object, required: true },
  days: { type: Array, default: () => [] },
  selectedDayNo: { type: Number, default: 0 },
})
defineEmits(['select'])

const WEEK = ['一', '二', '三', '四', '五', '六', '日']
const todayIso = new Date().toISOString().slice(0, 10)

const dayByIso = computed(() => {
  const m = {}
  for (const d of props.days) m[d.date] = d
  return m
})

function iso(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    + `-${String(d.getDate()).padStart(2, '0')}`
}

/** 一张连续的周网格,只铺行程所在的那几行,前后各多给一行。
 *
 *  原来是按自然月铺:一趟 14 天的行程只要跨了月,就画出两整月六十多格,
 *  绝大多数是空的,又长又难看。现在从"行程开始那一周的周一再往前一周"
 *  铺到"结束那一周的周日再往后一周",多出来的格子淡显,只为让人看清
 *  行程落在一周里的哪几天。 */
const cells = computed(() => {
  if (!props.trip?.start_date) return []
  const start = new Date(props.trip.start_date + 'T00:00:00')
  const end = new Date(props.trip.end_date + 'T00:00:00')

  const from = new Date(start)
  from.setDate(from.getDate() - ((from.getDay() + 6) % 7) - 7)   // 周一为首列
  const to = new Date(end)
  to.setDate(to.getDate() + (6 - ((to.getDay() + 6) % 7)) + 7)

  const out = []
  for (const d = new Date(from); d <= to; d.setDate(d.getDate() + 1)) {
    const key = iso(d)
    out.push({
      iso: key,
      dom: d.getDate(),
      month: d.getMonth() + 1,
      day: dayByIso.value[key] || null,
    })
  }
  return out
})

const spanLabel = computed(() => {
  const t = props.trip
  if (!t?.start_date) return ''
  const a = new Date(t.start_date + 'T00:00:00')
  const b = new Date(t.end_date + 'T00:00:00')
  const sameYear = a.getFullYear() === b.getFullYear()
  const head = `${a.getFullYear()} 年 ${a.getMonth() + 1} 月 ${a.getDate()} 日`
  const tail = sameYear
    ? `${b.getMonth() + 1} 月 ${b.getDate()} 日`
    : `${b.getFullYear()} 年 ${b.getMonth() + 1} 月 ${b.getDate()} 日`
  return `${head} — ${tail}`
})

/** 日历格子窄,路线只取目的地(箭头后那段),太长再截断。 */
function shortRoute(day) {
  const r = (day.route || '').trim()
  if (!r) return ''
  const dest = r.split(/[→>-]/).pop().trim() || r
  return dest.length > 6 ? dest.slice(0, 6) + '…' : dest
}

/** 当天的交通图标。
 *
 *  原来匹配不上就默认给 ✈️,结果几乎每天都挂着飞机——陆路 420km 也是飞机。
 *  现在先看地图停留点上的 air / sea 标记(那是结构化数据,最可信),
 *  再按文字匹配,**都认不出来就不显示**,而不是硬塞一个。 */
function transportIcon(day) {
  const stops = day?.detail?.stops || []
  if (stops.some(x => x && x.air)) return '✈️'
  if (stops.some(x => x && x.sea)) return '🚢'

  const s = (day?.transport || '').toLowerCase()
  if (!s) return ''
  if (/飞|航班|机场|空运|航空|fly|flight|air|✈/.test(s)) return '✈️'
  if (/船|邮轮|渡轮|快船|航船|ferry|cruise|⛴/.test(s)) return '🚢'
  if (/火车|高铁|铁路|列车|train|rail/.test(s)) return '🚆'
  if (/缆车|索道|cable/.test(s)) return '🚡'
  if (/巴士|大巴|客车|bus|coach/.test(s)) return '🚌'
  if (/自驾|租车|包车|专车|drive|car/.test(s)) return '🚗'
  if (/陆路|车程|公路|km|公里/.test(s)) return '🚌'
  if (/步行|徒步|walk/.test(s)) return '🚶'
  return ''
}
</script>

<style scoped>
.cal-span {
  font-size: 13px;
  font-weight: 700;
  color: var(--trip-ink-2, var(--color-text-muted));
  letter-spacing: .04em;
  margin-bottom: 8px;
}
.cal-mon {
  font-size: 10px;
  font-weight: 800;
  margin-right: 2px;
  color: var(--trip-accent, var(--color-primary));
}
.cal-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 6px;
}
.cal-wd {
  text-align: center;
  font-size: 11px;
  color: var(--color-text-muted);
  padding-bottom: 2px;
}

.cal-cell {
  position: relative;
  aspect-ratio: 1 / 1;
  min-height: 46px;
  border: 1px solid var(--trip-line, var(--color-border-light));
  border-radius: 10px;
  background: var(--trip-paper-2, var(--color-surface));
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  padding: 5px 6px;
  font: inherit;
  cursor: pointer;
  overflow: hidden;
  transition: transform .14s ease, box-shadow .14s ease, background .14s ease;
}
/* 行程外的那几格只为撑出一周的形状,淡显、不可点 */
.cal-cell.is-outside {
  opacity: .34;
  cursor: default;
  background: none;
}
/* 不在行程内的日子:可见但明显弱化,不可点 */

.cal-cell.in-trip:hover { transform: translateY(-2px); box-shadow: 0 4px 0 0 var(--shadow-anchor-light); }
.cal-cell.is-selected {
  border-color: var(--trip-accent, var(--color-primary));
  box-shadow: inset 0 0 0 1px var(--trip-accent, var(--color-primary));
  background: var(--trip-accent-weak, var(--color-primary-light));
}
.cal-cell.is-today .cal-date {
  background: var(--trip-accent, var(--color-primary));
  color: #fff;
  border-radius: 999px;
  padding: 0 5px;
}

.cal-date { font-size: 12px; font-weight: 700; color: var(--color-text); font-variant-numeric: tabular-nums; }
.cal-dayno { font-size: 10px; font-weight: 700; color: var(--trip-accent, var(--color-primary)); }
.cal-route {
  font-size: 10px;
  color: var(--color-text-muted);
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}
.cal-icon { position: absolute; right: 4px; top: 4px; font-size: 10px; }
.cal-flag { position: absolute; right: 4px; bottom: 3px; font-size: 10px; color: var(--trip-accent, var(--color-primary)); }

/* 移动端竖屏:格子更紧凑,路线文字让位给日期 + 天数。
   交通图标留着——一眼扫过去哪天飞、哪天坐车,比路线文字更有用,也不占地方。 */
@media (max-width: 768px) {
  .cal-grid { gap: 4px; }
  .cal-cell { min-height: 44px; padding: 3px 4px; border-radius: 8px; }
  .cal-route { display: none; }
  .cal-icon { right: 3px; top: 3px; font-size: 11px; }
}
</style>
