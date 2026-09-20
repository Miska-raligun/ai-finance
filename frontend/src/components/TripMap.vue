<!-- components/TripMap.vue — 行程地图:海岸线底图 + 路线折线 + 可点景点
     底图为 Natural Earth 110m 陆地(公有领域)简化后的静态资源,按需懒加载,
     不依赖任何外部地图服务——既避开 CSP(default-src 'self'),也不把行程
     坐标发给第三方。 -->
<template>
  <div class="tmap" ref="wrapRef">
    <div class="tmap-head">
      <span class="tmap-title">{{ title }}</span>
      <div class="tmap-tools">
        <el-button size="small" text :disabled="scale === 1" @click="resetView">复位</el-button>
        <span class="tmap-hint">滚轮缩放 · 拖动平移 · 点圆点看介绍</span>
      </div>
    </div>

    <svg
      ref="svgRef"
      class="tmap-svg"
      :viewBox="`0 0 ${W} ${H}`"
      role="img"
      :aria-label="`${title} 地图`"
      @wheel.prevent="onWheel"
      @pointerdown="onDown"
      @pointermove="onMove"
      @pointerup="onUp"
      @pointerleave="onUp"
    >
      <g :transform="`translate(${tx} ${ty}) scale(${scale})`">
        <!-- 陆地 -->
        <path v-if="landPath" :d="landPath" class="tmap-land" />
        <!-- 路线:按天顺序连接 -->
        <path v-if="routePath" :d="routePath" class="tmap-route" :style="{ strokeWidth: 2 / scale }" />
        <!-- 景点 -->
        <g v-for="(p, i) in points" :key="i">
          <circle
            :cx="p.x" :cy="p.y" :r="(p.id === activeId ? 6 : 4) / scale"
            :class="['tmap-dot', { on: p.id === activeId, air: p.air, sea: p.sea }]"
            :style="{ strokeWidth: 1.5 / scale }"
            tabindex="0"
            role="button"
            :aria-label="p.t"
            @click.stop="select(p)"
            @keydown.enter.stop="select(p)"
          />
        </g>
      </g>
    </svg>

    <!-- 景点介绍卡 -->
    <transition name="tmap-pop">
      <div v-if="active" class="tmap-pop">
        <button class="tmap-pop-x" aria-label="关闭" @click="active = null">×</button>
        <div class="tmap-pop-day" v-if="active.dayLabel">{{ active.dayLabel }}</div>
        <div class="tmap-pop-t">{{ active.t }}</div>
        <div v-if="active.dur" class="tmap-pop-meta">{{ active.dur }}</div>
        <p v-if="active.desc" class="tmap-pop-desc">{{ active.desc }}</p>
        <p v-else class="tmap-pop-desc tmap-pop-empty">这个点还没有介绍。</p>
      </div>
    </transition>

    <!-- 景点列表:全程视图下市内景点会挤成一点、互相遮挡,列表保证每个点都可达,
         也让键盘/读屏用户能选中 -->
    <ul v-if="points.length" class="tmap-list">
      <li v-for="p in points" :key="p.id">
        <button
          type="button"
          class="tmap-li"
          :class="{ on: p.id === activeId }"
          @click="select(p)"
        >
          <span class="tmap-li-dot" :class="{ air: p.air, sea: p.sea }" aria-hidden="true"></span>
          <span class="tmap-li-t">{{ p.t }}</span>
          <span class="tmap-li-day">D{{ p.id.split('-')[0] }}</span>
        </button>
      </li>
    </ul>

    <div v-if="!points.length" class="tmap-empty">
      这段行程还没有标注坐标的景点。在每天的详情里给 stops 填上经纬度即可显示。
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'

const props = defineProps({
  // [{ day_no, date, route, detail:{ stops:[{t,lat,lng,air,sea,desc}], spots } }]
  days: { type: Array, default: () => [] },
  title: { type: String, default: '全程路线' },
})

const W = 760, H = 380
const svgRef = ref(null)
const land = ref(null)
const active = ref(null)
const scale = ref(1)
const tx = ref(0), ty = ref(0)

// 底图按需加载:只有真正打开地图才拉这 21KB(gzip),不拖累首屏
onMounted(async () => {
  try {
    const mod = await import('@/assets/geo/world-land.json')
    land.value = mod.default || mod
  } catch {
    land.value = []      // 底图挂了也不影响景点和路线显示
  }
})

/** 收集所有带坐标的点,按天顺序;景点介绍从 spots 里按名字配对补齐。 */
const rawPoints = computed(() => {
  const out = []
  for (const d of props.days) {
    const detail = d.detail || {}
    const spotDesc = {}
    for (const s of (detail.spots || [])) {
      if (Array.isArray(s) && s[0]) spotDesc[s[0]] = s[1] || ''
    }
    for (const st of (detail.stops || [])) {
      const lat = Number(st.lat), lng = Number(st.lng)
      if (!isFinite(lat) || !isFinite(lng)) continue
      out.push({
        id: `${d.day_no}-${out.length}`,
        t: st.t || '未命名',
        lat, lng, air: !!st.air, sea: !!st.sea,
        desc: st.desc || st.note || '',
        dur: spotDesc[st.t] || '',
        dayLabel: `Day ${d.day_no} · ${d.route || d.date || ''}`.trim(),
      })
    }
  }
  return out
})

/** 取自动 fit 用的外接框。

 *  直接用全部点的外接框有个很难看的后果:一条「上海 ✈ 赫尔辛基」的长途航段
 *  会把视野撑到半个欧亚大陆,真正要看的北欧部分缩成一小团。所以这里先算
 *  中间 90% 的点的框,只有当它比全量框小一半以上(说明确实存在远端离群点)
 *  才采用;点少或分布均匀时两者几乎一样,行为不变。被排除的点照样画出来,
 *  只是落在视野外,缩小地图就能看到。
 */
function fitBox(pts) {
  const lats = pts.map(p => p.lat).sort((a, b) => a - b)
  const lngs = pts.map(p => p.lng).sort((a, b) => a - b)
  const at = (arr, t) => arr[Math.max(0, Math.min(arr.length - 1, Math.round((arr.length - 1) * t)))]
  const full = {
    minLat: lats[0], maxLat: lats[lats.length - 1],
    minLng: lngs[0], maxLng: lngs[lngs.length - 1],
  }
  if (pts.length < 8) return full
  const core = {
    minLat: at(lats, 0.05), maxLat: at(lats, 0.95),
    minLng: at(lngs, 0.05), maxLng: at(lngs, 0.95),
  }
  const area = (b) => Math.max(b.maxLat - b.minLat, 1e-6) * Math.max(b.maxLng - b.minLng, 1e-6)
  return area(core) < area(full) * 0.5 ? core : full
}

/** 等距圆柱投影 + 自动 fit(带 padding,并按纬度修正横向压缩)。 */
const proj = computed(() => {
  const pts = rawPoints.value
  if (!pts.length) return null
  let { minLat, maxLat, minLng, maxLng } = fitBox(pts)
  // 单点或极小范围时给一个最小跨度,避免除零和过度放大
  const padLat = Math.max((maxLat - minLat) * 0.25, 0.6)
  const padLng = Math.max((maxLng - minLng) * 0.25, 0.9)
  minLat -= padLat; maxLat += padLat; minLng -= padLng; maxLng += padLng

  const midLat = (minLat + maxLat) / 2
  const kx = Math.cos(midLat * Math.PI / 180)   // 高纬度经度要按 cos 压缩,否则被拉宽
  const spanX = (maxLng - minLng) * kx
  const spanY = (maxLat - minLat)
  const s = Math.min(W / spanX, H / spanY)
  const offX = (W - spanX * s) / 2
  const offY = (H - spanY * s) / 2
  return {
    x: (lng) => offX + (lng - minLng) * kx * s,
    y: (lat) => offY + (maxLat - lat) * s,
    bbox: { minLat, maxLat, minLng, maxLng },
  }
})

const points = computed(() => {
  const pr = proj.value
  if (!pr) return []
  return rawPoints.value.map(p => ({ ...p, x: pr.x(p.lng), y: pr.y(p.lat) }))
})

const landPath = computed(() => {
  const pr = proj.value
  if (!pr || !land.value) return ''
  const { minLat, maxLat, minLng, maxLng } = pr.bbox
  const parts = []
  for (const ring of land.value) {
    // 只画与当前视野相交的环,省掉全球其它大陆的绘制
    let hit = false
    for (const [lng, lat] of ring) {
      if (lng >= minLng - 25 && lng <= maxLng + 25 && lat >= minLat - 15 && lat <= maxLat + 15) { hit = true; break }
    }
    if (!hit) continue
    let d = ''
    for (let i = 0; i < ring.length; i++) {
      const [lng, lat] = ring[i]
      d += (i ? 'L' : 'M') + pr.x(lng).toFixed(1) + ' ' + pr.y(lat).toFixed(1)
    }
    parts.push(d + 'Z')
  }
  return parts.join('')
})

const routePath = computed(() => {
  const ps = points.value
  if (ps.length < 2) return ''
  return ps.map((p, i) => (i ? 'L' : 'M') + p.x.toFixed(1) + ' ' + p.y.toFixed(1)).join('')
})

const activeId = computed(() => active.value?.id || null)
function select(p) { active.value = p }

watch(() => props.days, () => { active.value = null; resetView() })

// ---- 缩放 / 平移 ----
function resetView() { scale.value = 1; tx.value = 0; ty.value = 0 }

const MIN_SCALE = 0.35   // 允许缩到 1 倍以下,才能把 fit 之外的远端点拉回视野

function onWheel(e) {
  const next = Math.min(8, Math.max(MIN_SCALE, scale.value * (e.deltaY < 0 ? 1.15 : 1 / 1.15)))
  if (next === scale.value) return
  // 以指针位置为锚点缩放,手感更自然
  const r = svgRef.value.getBoundingClientRect()
  const mx = (e.clientX - r.left) / r.width * W
  const my = (e.clientY - r.top) / r.height * H
  tx.value = mx - (mx - tx.value) * (next / scale.value)
  ty.value = my - (my - ty.value) * (next / scale.value)
  scale.value = next
  if (next === 1) { tx.value = 0; ty.value = 0 }
}

let drag = null
function onDown(e) {
  if (scale.value === 1) return
  drag = { x: e.clientX, y: e.clientY, tx: tx.value, ty: ty.value }
  svgRef.value.setPointerCapture?.(e.pointerId)
}
function onMove(e) {
  if (!drag) return
  const r = svgRef.value.getBoundingClientRect()
  tx.value = drag.tx + (e.clientX - drag.x) / r.width * W
  ty.value = drag.ty + (e.clientY - drag.y) / r.height * H
}
function onUp() { drag = null }
</script>

<style scoped>
.tmap { position: relative; }
.tmap-head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
.tmap-title { font-size: 12px; font-weight: 800; letter-spacing: .08em; color: var(--trip-ink-2, var(--color-text-muted)); }
.tmap-tools { display: flex; align-items: center; gap: 8px; }
.tmap-hint { font-size: 11px; color: var(--color-text-muted); }

.tmap-svg {
  width: 100%;
  height: auto;
  display: block;
  background: var(--trip-accent-weak, var(--color-surface-2));
  border-radius: 12px;
  border: 1px solid var(--trip-line, var(--color-border-light));
  touch-action: none;
  cursor: grab;
}
.tmap-svg:active { cursor: grabbing; }

.tmap-land { fill: var(--color-surface); stroke: var(--trip-line, var(--color-border-light)); stroke-width: .5; }
.tmap-route {
  fill: none;
  stroke: var(--trip-accent, var(--color-primary));
  stroke-linejoin: round;
  stroke-linecap: round;
  stroke-dasharray: 5 4;
  opacity: .85;
}
.tmap-dot {
  fill: var(--color-surface);
  stroke: var(--trip-accent, var(--color-primary));
  cursor: pointer;
  transition: fill .12s ease;
}
.tmap-dot:hover, .tmap-dot:focus-visible { fill: var(--trip-accent, var(--color-primary)); outline: none; }
.tmap-dot.on { fill: var(--trip-accent, var(--color-primary)); }
.tmap-dot.air { stroke-dasharray: 2 1.6; }
.tmap-dot.sea { stroke-width: 2; }

.tmap-pop {
  position: absolute; right: 10px; bottom: 10px; max-width: 62%;
  background: var(--color-surface);
  border: 2px solid var(--trip-accent, var(--color-primary));
  border-radius: 12px; padding: 10px 30px 10px 12px;
  box-shadow: 0 4px 0 0 var(--shadow-anchor-light);
}
.tmap-pop-x {
  position: absolute; right: 6px; top: 4px; border: 0; background: none;
  font-size: 17px; line-height: 1; cursor: pointer; color: var(--color-text-muted);
}
.tmap-pop-day { font-size: 10px; letter-spacing: .05em; color: var(--trip-accent, var(--color-primary)); font-weight: 700; }
.tmap-pop-t { font-size: 14px; font-weight: 800; color: var(--color-text-strong); margin-top: 2px; }
.tmap-pop-meta { font-size: 11px; color: var(--color-text-muted); margin-top: 1px; }
.tmap-pop-desc { font-size: 12px; line-height: 1.6; color: var(--color-text); margin: 6px 0 0; }
.tmap-pop-empty { color: var(--color-text-muted); }
.tmap-pop-enter-active, .tmap-pop-leave-active { transition: opacity .16s ease, transform .16s ease; }
.tmap-pop-enter-from, .tmap-pop-leave-to { opacity: 0; transform: translateY(6px); }

.tmap-list {
  list-style: none; margin: 10px 0 0; padding: 0;
  display: flex; flex-wrap: wrap; gap: 6px;
  max-height: 132px; overflow-y: auto;
}
.tmap-li {
  display: inline-flex; align-items: center; gap: 6px;
  appearance: none; border: 1px solid var(--trip-line, var(--color-border-light));
  background: var(--color-surface); color: var(--color-text);
  font: inherit; font-size: 12px; padding: 3px 9px; border-radius: 999px; cursor: pointer;
}
.tmap-li:hover { border-color: var(--trip-accent, var(--color-primary)); }
.tmap-li.on {
  background: var(--trip-accent, var(--color-primary)); color: #fff;
  border-color: var(--trip-accent, var(--color-primary));
}
.tmap-li-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
  border: 1.5px solid var(--trip-accent, var(--color-primary)); background: transparent;
}
.tmap-li.on .tmap-li-dot { background: #fff; border-color: #fff; }
.tmap-li-day { font-size: 10px; opacity: .65; font-variant-numeric: tabular-nums; }

.tmap-empty { padding: 14px 4px 2px; font-size: 12px; color: var(--color-text-muted); }

@media (max-width: 768px) {
  .tmap-hint { display: none; }
  .tmap-pop { max-width: calc(100% - 20px); left: 10px; right: 10px; }
}
</style>
