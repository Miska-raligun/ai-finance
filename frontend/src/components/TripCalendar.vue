<!-- components/TripCalendar.vue — 行程日历:按月网格铺开,行程内的日子显示当天概览 -->
<template>
  <div class="cal">
    <div v-for="m in months" :key="m.key" class="cal-month">
      <div class="cal-month-title">{{ m.label }}</div>

      <div class="cal-grid" role="grid">
        <div v-for="w in WEEK" :key="w" class="cal-wd" role="columnheader">{{ w }}</div>

        <button
          v-for="(cell, i) in m.cells"
          :key="i"
          class="cal-cell"
          :class="{
            'is-blank': !cell,
            'in-trip': cell && cell.day,
            'is-selected': cell && cell.day && cell.day.day_no === selectedDayNo,
            'is-today': cell && cell.iso === todayIso,
          }"
          :disabled="!cell || !cell.day"
          :aria-selected="!!(cell && cell.day && cell.day.day_no === selectedDayNo)"
          role="gridcell"
          @click="cell && cell.day && $emit('select', cell.day.day_no)"
        >
          <template v-if="cell">
            <span class="cal-date">{{ cell.dom }}</span>
            <template v-if="cell.day">
              <span class="cal-dayno">D{{ cell.day.day_no }}</span>
              <span class="cal-route">{{ shortRoute(cell.day) }}</span>
              <span v-if="cell.day.transport" class="cal-icon" :title="cell.day.transport">
                {{ transportIcon(cell.day.transport) }}
              </span>
              <span v-if="cell.day.journal" class="cal-flag" title="已有手记">✎</span>
            </template>
          </template>
        </button>
      </div>
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

/** 行程跨越的每个自然月各渲染一张网格(周一为首列,空位补 null)。 */
const months = computed(() => {
  if (!props.trip?.start_date) return []
  const start = new Date(props.trip.start_date + 'T00:00:00')
  const end = new Date(props.trip.end_date + 'T00:00:00')
  const out = []
  const cur = new Date(start.getFullYear(), start.getMonth(), 1)
  while (cur <= end) {
    const y = cur.getFullYear(), mo = cur.getMonth()
    const first = new Date(y, mo, 1)
    const daysInMonth = new Date(y, mo + 1, 0).getDate()
    // JS getDay(): 0=周日 → 转成周一为 0
    const lead = (first.getDay() + 6) % 7
    const cells = new Array(lead).fill(null)
    for (let d = 1; d <= daysInMonth; d++) {
      const iso = `${y}-${String(mo + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
      cells.push({ iso, dom: d, day: dayByIso.value[iso] || null })
    }
    out.push({ key: `${y}-${mo}`, label: `${y} 年 ${mo + 1} 月`, cells })
    cur.setMonth(mo + 1)
  }
  return out
})

/** 日历格子窄,路线只取目的地(箭头后那段),太长再截断。 */
function shortRoute(day) {
  const r = (day.route || '').trim()
  if (!r) return ''
  const dest = r.split(/[→>-]/).pop().trim() || r
  return dest.length > 6 ? dest.slice(0, 6) + '…' : dest
}

function transportIcon(t) {
  const s = (t || '').toLowerCase()
  if (/船|邮轮|ferry|cruise/.test(s)) return '🚢'
  if (/火车|铁路|train|rail/.test(s)) return '🚆'
  if (/巴士|大巴|bus|coach/.test(s)) return '🚌'
  if (/自驾|租车|drive|car/.test(s)) return '🚗'
  return '✈️'
}
</script>

<style scoped>
.cal-month + .cal-month { margin-top: 18px; }
.cal-month-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--trip-ink-2, var(--color-text-muted));
  letter-spacing: .04em;
  margin-bottom: 8px;
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
.cal-cell.is-blank { border: none; background: none; cursor: default; }
/* 不在行程内的日子:可见但明显弱化,不可点 */
.cal-cell:not(.in-trip):not(.is-blank) { opacity: .38; cursor: default; }
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

/* 移动端竖屏:格子更紧凑,路线文字让位给日期+天数 */
@media (max-width: 768px) {
  .cal-grid { gap: 4px; }
  .cal-cell { min-height: 40px; padding: 3px 4px; border-radius: 8px; }
  .cal-route { display: none; }
  .cal-icon { display: none; }
}
</style>
