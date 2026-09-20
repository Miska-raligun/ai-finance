<!-- components/TripMap.vue — 行程地图:海岸线底图 + 曲线航段 + 带标注的停留点
     底图为 Natural Earth 110m 陆地(公有领域)简化后的静态资源,按需懒加载,
     不依赖任何外部地图服务——既避开 CSP(default-src 'self'),也不把行程
     坐标发给第三方。

     标注是这张图能不能看懂的关键:只有圆点的话,在没有地名的底图上根本
     认不出是哪儿。所以做了「就近合并 + 避让排版」,放不下的标签宁可不画,
     也不让它们互相压。 -->
<template>
  <div class="tmap" ref="wrapRef">
    <div class="tmap-head">
      <span class="tmap-title">{{ title }}</span>
      <div class="tmap-tools">
        <button type="button" class="tmap-btn" :disabled="zoom === 1" @click="resetView">复位</button>
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
      <rect class="tmap-sea" :width="W" :height="H" />

      <!-- 陆地:跟着视图缩放,描边用 non-scaling-stroke 保持粗细 -->
      <g v-if="landPath" :transform="landTransform">
        <path :d="landPath" class="tmap-land" vector-effect="non-scaling-stroke" />
      </g>

      <!-- 航段:曲线。飞行虚线、航船点线、陆路实线 -->
      <path
        v-for="(l, i) in legs"
        :key="'l' + i"
        :d="l.d"
        class="tmap-leg"
        :class="{ air: l.air, sea: l.sea }"
      />

      <!-- 标签引线 -->
      <line
        v-for="(g, i) in labels.filter(x => x.lead)"
        :key="'g' + i"
        class="tmap-lead"
        :x1="g.mx" :y1="g.my" :x2="g.lx" :y2="g.ly"
      />

      <!-- 停留点 -->
      <g
        v-for="m in marks"
        :key="m.key"
        class="tmap-mark"
        :class="{ on: m.key === activeKey }"
        role="button"
        tabindex="0"
        :aria-label="m.label"
        @click.stop="open(m)"
        @keydown.enter.stop="open(m)"
      >
        <circle :cx="m.x" :cy="m.y" :r="m.r + 2.2" class="tmap-ring" />
        <circle
          :cx="m.x" :cy="m.y" :r="m.r"
          class="tmap-dot"
          :class="{ first: m.first, last: m.last }"
        />
        <!-- 合并了几个点时角标写数量 -->
        <g v-if="m.stops.length > 1">
          <circle :cx="m.x + m.r + 2.6" :cy="m.y - m.r - 1.6" r="5.6" class="tmap-badge" />
          <text :x="m.x + m.r + 2.6" :y="m.y - m.r + 1.2" class="tmap-badge-t">{{ m.stops.length }}</text>
        </g>
        <!-- 命中区:圆点太小,给一个不可见的大圆兜住点击 -->
        <circle :cx="m.x" :cy="m.y" r="13" class="tmap-hit" />
      </g>

      <!-- 标签 -->
      <g v-for="(g, i) in labels" :key="'t' + i" class="tmap-label" @click.stop="open(g.mark)">
        <rect :x="g.bx" :y="g.by" :width="g.bw" :height="g.bh" rx="3" class="tmap-chip" />
        <text :x="g.tx" :y="g.ty" :text-anchor="g.anchor" class="tmap-chip-t">{{ g.text }}</text>
      </g>
    </svg>

    <div class="tmap-legend">
      <span v-if="hasAir"><i class="lg lg-air"></i>飞行</span>
      <span v-if="hasSea"><i class="lg lg-sea"></i>航船</span>
      <span><i class="lg lg-road"></i>陆路</span>
      <span><i class="dotl start"></i>起点</span>
      <span><i class="dotl end"></i>终点</span>
    </div>

    <!-- 停留点列表:全程视图下市内景点会挤成一点,列表保证每个点都可达,
         也让键盘 / 读屏用户有路径。 -->
    <ul v-if="points.length" class="tmap-list">
      <li v-for="p in points" :key="p.id">
        <button
          type="button"
          class="tmap-li"
          :class="{ on: activeStopId === p.id }"
          @click="openStop(p)"
        >
          <span class="tmap-li-dot" :class="{ air: p.air, sea: p.sea }"></span>
          {{ p.t }}
          <span class="tmap-li-day">D{{ p.dayNo }}</span>
        </button>
      </li>
    </ul>
    <div v-else class="tmap-empty">这段行程还没有标记地点。</div>

    <!-- 景点详情:大窗口 -->
    <teleport to="body">
      <div v-if="detail" class="spot-mask" @click.self="detail = null">
        <div class="spot" :style="accentStyle" role="dialog" aria-modal="true">
          <button class="spot-x" aria-label="关闭" @click="detail = null">×</button>

          <div class="spot-photo" :class="{ empty: !detail.photo }">
            <img v-if="detail.photo" :src="detail.photo" :alt="detail.t" />
            <div v-else class="spot-photo-ph">
              <span>{{ detail.t.slice(0, 1) }}</span>
            </div>
            <div v-if="canEdit" class="spot-photo-act">
              <button type="button" :disabled="saving" @click="fileRef?.click()">
                {{ detail.photo ? '换一张' : '＋ 加张照片' }}
              </button>
              <button v-if="detail.photo" type="button" :disabled="saving" @click="removePhoto">
                移除
              </button>
              <input
                ref="fileRef"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                hidden
                @change="onPickPhoto"
              >
            </div>
          </div>

          <div class="spot-body">
            <div class="spot-top">
              <span class="spot-day">Day {{ detail.dayNo }}</span>
              <span v-if="detail.date" class="spot-date">{{ detail.date }}</span>
              <span v-if="detail.air" class="spot-tag">✈ 航段</span>
              <span v-else-if="detail.sea" class="spot-tag">⛴ 航船</span>
            </div>

            <h3 class="spot-t">{{ detail.t }}</h3>
            <div v-if="detail.dur || detail.route" class="spot-meta">
              <span v-if="detail.dur">停留 {{ detail.dur }}</span>
              <span v-if="detail.route">{{ detail.route }}</span>
            </div>

            <template v-if="editing">
              <textarea
                v-model="draft"
                class="spot-edit"
                rows="5"
                placeholder="写点介绍：为什么值得来、看什么、注意什么…"
              ></textarea>
              <div class="spot-edit-foot">
                <button type="button" class="spot-b" @click="editing = false">取消</button>
                <button type="button" class="spot-b primary" :disabled="saving" @click="saveDesc">
                  {{ saving ? '保存中…' : '保存' }}
                </button>
              </div>
            </template>
            <template v-else>
              <p v-if="detail.desc" class="spot-desc">{{ detail.desc }}</p>
              <p v-else class="spot-desc spot-desc-none">这个点还没有写介绍。</p>
              <button v-if="canEdit" type="button" class="spot-edit-b" @click="startEdit">
                ✎ {{ detail.desc ? '改介绍' : '写介绍' }}
              </button>
            </template>

            <p v-if="uploadErr" class="spot-err">{{ uploadErr }}</p>

            <div v-if="detail.tips.length" class="spot-tips">
              <h4>相关贴士</h4>
              <ul><li v-for="(t, i) in detail.tips" :key="i">{{ t }}</li></ul>
            </div>

            <!-- 同一个点合并了多个地名时,可以直接切换 -->
            <div v-if="siblings.length > 1" class="spot-sib">
              <span>这一带还有:</span>
              <button
                v-for="s in siblings"
                :key="s.id"
                type="button"
                class="spot-sib-b"
                :class="{ on: s.id === detail.id }"
                @click="detail = describe(s)"
              >{{ s.t }}</button>
            </div>

            <a
              v-if="detail.mapUrl"
              class="spot-map"
              :href="detail.mapUrl"
              target="_blank"
              rel="noopener noreferrer"
            >📍 在地图应用里打开</a>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { mapUrl } from '@/utils/maplink'

const props = defineProps({
  // [{ day_no, date, route, detail:{ stops:[{t,lat,lng,air,sea,desc,photo}], spots, todo, cam, warn } }]
  days: { type: Array, default: () => [] },
  title: { type: String, default: '全程路线' },
  // 给了 tripId 才能改介绍 / 传照片;公开分享页只给 shareToken,永远只读
  tripId: { type: Number, default: 0 },
  shareToken: { type: String, default: '' },
})
const emit = defineEmits(['changed'])

const canEdit = computed(() => !!props.tripId && !props.shareToken)

/** 停留点只存 sha,URL 前缀在私有页和分享页是两套。 */
function photoUrl(sha) {
  if (!sha) return ''
  return props.shareToken
    ? `/api/public/trips/${encodeURIComponent(props.shareToken)}/photos/${sha}`
    : (props.tripId ? `/api/trips/${props.tripId}/photos/${sha}` : '')
}

const W = 760, H = 380
const S = 100                      // 世界坐标缩放基数
const wrapRef = ref(null)
const svgRef = ref(null)
const land = ref(null)
const detail = ref(null)
const activeStopId = ref(null)
const zoom = ref(1)
const panX = ref(0), panY = ref(0)

// 弹窗 teleport 到 body,拿不到外层 .travel-page 上的主题色变量,
// 打开时从组件所在位置把它们读出来带过去。
const ACCENT_VARS = ['--trip-accent', '--trip-accent-weak', '--trip-accent-ink']
const accentStyle = ref({})
function snapshotAccent() {
  const el = wrapRef.value
  if (!el) return
  const cs = getComputedStyle(el)
  const out = {}
  for (const k of ACCENT_VARS) {
    const v = cs.getPropertyValue(k).trim()
    if (v) out[k] = v
  }
  accentStyle.value = out
}

onMounted(async () => {
  try {
    const mod = await import('@/assets/geo/world-land.json')
    land.value = mod.default || mod
  } catch {
    land.value = []                // 底图挂了也不影响景点和路线
  }
})

/* ---------- 取点 ---------- */

/** 收集所有带坐标的点,按天顺序;顺带把当天 spots 的时长、
 *  以及提到这个地名的贴士配对上去——静态行程页里介绍是散在
 *  spots / todo / cam 里的,不配对的话点开只会看到一句"还没有介绍"。 */
const points = computed(() => {
  const out = []
  for (const d of props.days) {
    const det = d.detail || {}
    const durOf = {}
    for (const s of (det.spots || [])) {
      if (Array.isArray(s) && s[0]) durOf[s[0]] = s[1] || ''
    }
    const tipPool = [...(det.todo || []), ...(det.cam || []), ...(det.warn || [])]
    const stops = det.stops || []
    for (let si = 0; si < stops.length; si++) {
      const st = stops[si]
      const lat = Number(st.lat), lng = Number(st.lng)
      if (!isFinite(lat) || !isFinite(lng)) continue
      const name = st.t || '未命名'
      out.push({
        id: `${d.day_no}-${out.length}`,
        si,
        t: name,
        lat, lng,
        air: !!st.air, sea: !!st.sea,
        desc: st.desc || st.note || '',
        photoSha: st.photo || '',
        dur: durOf[name] || '',
        // 贴士里点名提到这个地点的,归到它名下
        tips: tipPool.filter(x => typeof x === 'string' && x.includes(name)),
        dayNo: d.day_no,
        date: d.date || '',
        route: d.route || '',
      })
    }
  }
  return out
})

const hasAir = computed(() => points.value.some(p => p.air))
const hasSea = computed(() => points.value.some(p => p.sea))

/* ---------- 投影与视图 ---------- */

/** 取自动 fit 用的外接框。
 *
 *  直接用全部点的外接框有个很难看的后果:一条「上海 ✈ 赫尔辛基」的长途航段
 *  会把视野撑到半个欧亚大陆,真正要看的北欧部分缩成一小团。所以这里先算
 *  中间 90% 的点的框,只有当它比全量框小一半以上(说明确实存在远端离群点)
 *  才采用;点少或分布均匀时两者几乎一样,行为不变。 */
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

// 高纬度经度要按 cos 压缩,否则地图被横向拉宽
const K = computed(() => {
  const pts = points.value
  if (!pts.length) return 1
  const b = fitBox(pts)
  return Math.cos(((b.minLat + b.maxLat) / 2) * Math.PI / 180)
})
const wx = (lng) => lng * K.value * S
const wy = (lat) => -lat * S

/** 基准视图:把 fit 框放进画布,四周留白。 */
const baseView = computed(() => {
  const pts = points.value
  if (!pts.length) return { cx: 0, cy: 0, s: 1 }
  const b = fitBox(pts)
  const x0 = wx(b.minLng), x1 = wx(b.maxLng)
  const y0 = wy(b.maxLat), y1 = wy(b.minLat)
  const pad = 54                      // 给标签留的边距
  const dx = Math.max(x1 - x0, 1e-6), dy = Math.max(y1 - y0, 1e-6)
  return {
    cx: (x0 + x1) / 2,
    cy: (y0 + y1) / 2,
    s: Math.min((W - pad * 2) / dx, (H - pad * 2) / dy),
  }
})

const view = computed(() => {
  const b = baseView.value
  const s = b.s * zoom.value
  return { cx: b.cx - panX.value / s, cy: b.cy - panY.value / s, s }
})

function screen(p) {
  const v = view.value
  return [(wx(p.lng) - v.cx) * v.s + W / 2, (wy(p.lat) - v.cy) * v.s + H / 2]
}

const landTransform = computed(() => {
  const v = view.value
  return `translate(${(W / 2 - v.cx * v.s).toFixed(2)} ${(H / 2 - v.cy * v.s).toFixed(2)}) scale(${v.s.toFixed(6)})`
})

// 底图路径只跟 K 有关,缩放平移交给 transform,不用每帧重算这 120 个环。
// 只画与视野相交的环:一是省掉全球其它大陆的绘制,二是更要紧的——
// 欧亚和美洲这种跨半球的大环一起画进同一个 <path> 时,绕向相反的环在
// nonzero 填充下会互相翻转,海面会被整片涂成陆地色。
const landPath = computed(() => {
  if (!land.value || !land.value.length) return ''
  const k = K.value
  const pts = points.value
  if (!pts.length) return ''
  const b = fitBox(pts)
  // 留足余量,缩到最小(0.35)时四周也还有陆地
  const win = {
    minLng: b.minLng - 45, maxLng: b.maxLng + 45,
    minLat: b.minLat - 28, maxLat: b.maxLat + 28,
  }
  const parts = []
  for (const ring of land.value) {
    let hit = false
    for (const [lng, lat] of ring) {
      if (lng >= win.minLng && lng <= win.maxLng && lat >= win.minLat && lat <= win.maxLat) {
        hit = true
        break
      }
    }
    if (!hit) continue
    let d = ''
    for (let i = 0; i < ring.length; i++) {
      const [lng, lat] = ring[i]
      d += (i ? 'L' : 'M') + (lng * k * S).toFixed(1) + ' ' + (-lat * S).toFixed(1)
    }
    parts.push(d + 'Z')
  }
  return parts.join('')
})

/* ---------- 航段:曲线 ---------- */

/** 两点之间画一条二次贝塞尔,控制点沿弦的垂线外推。
 *  直线看起来像网络拓扑图,弧线才像航线;飞行段拱得更明显一点。 */
const legs = computed(() => {
  const ps = points.value
  const out = []
  for (let i = 1; i < ps.length; i++) {
    const [ax, ay] = screen(ps[i - 1])
    const [bx, by] = screen(ps[i])
    const dx = bx - ax, dy = by - ay
    const len = Math.hypot(dx, dy)
    if (len < 2) continue
    const bend = (ps[i].air ? 0.17 : 0.09)
    // 垂线方向统一取一侧,整条路线的弧向才一致
    const mx = (ax + bx) / 2 - dy * bend
    const my = (ay + by) / 2 + dx * bend
    out.push({
      d: `M${ax.toFixed(1)} ${ay.toFixed(1)}Q${mx.toFixed(1)} ${my.toFixed(1)} ${bx.toFixed(1)} ${by.toFixed(1)}`,
      air: !!ps[i].air,
      sea: !!ps[i].sea,
    })
  }
  return out
})

/* ---------- 就近合并 ---------- */

const MERGE_PX = 20

/** 一堆点挤在一起时,标签该写哪个名字。
 *
 *  地图上要的是"这是哪座城",不是"这一团里排第一的那个景点"。取被同团其它
 *  名字包含得最多的那个:赫尔辛基机场 / 赫尔辛基之眼 / 赫尔辛基 → 赫尔辛基。
 *  并列时保留行程里最早出现的那个——当天第一个点通常是机场 / 港口 / 进城点,
 *  比"老城""新港"这种到处都有的名字更能定位。
 *
 *  试过拿当天 route 里的地名加权,但那些是行程描述不是地名层级:
 *  「南岸瀑布 · DC3 · 维克黑沙滩」会把一整团标成 DC3,反而更糟。 */
function pickName(names) {
  let best = names[0], bestScore = -1
  for (const n of names) {
    const score = names.reduce((k, o) => k + (o.includes(n) ? 1 : 0), 0)
    if (score > bestScore) {
      best = n
      bestScore = score
    }
  }
  return best
}

const marks = computed(() => {
  const ps = points.value
  const out = []
  ps.forEach((p, i) => {
    const [x, y] = screen(p)
    const hit = out.find(o => Math.hypot(o.x - x, o.y - y) < MERGE_PX)
    if (hit) {
      hit.stops.push(p)
      if (i === 0) hit.first = true
      if (i === ps.length - 1) hit.last = true
      return
    }
    out.push({
      key: p.id, x, y, stops: [p],
      first: i === 0, last: i === ps.length - 1,
    })
  })
  for (const m of out) {
    const names = [...new Set(m.stops.map(s => s.t))]
    const joined = names.join(' · ')
    m.label = joined.length <= 14 ? joined : `${pickName(names)} 等 ${names.length} 处`
    m.r = (m.first || m.last) ? 5.2 : 4
    // 起终点和合并点优先拿到标签位
    m.pri = (m.first || m.last) ? 0 : (m.stops.length > 1 ? 1 : 2)
  }
  return out
})

const activeKey = computed(() => {
  const id = activeStopId.value
  if (!id) return null
  return marks.value.find(m => m.stops.some(s => s.id === id))?.key || null
})

/* ---------- 标签避让 ---------- */

const FS = 11.5

/** 中日文按全宽、西文按 0.56 倍估宽度,够排版用。 */
function textWidth(t) {
  let w = 0
  for (const ch of t) w += /[　-鿿＀-￯]/.test(ch) ? FS : FS * 0.56
  return w
}

/** 逐个找不与已放标签 / 圆点相撞的位置,两圈候选方向都放不下就放弃。
 *  宁可少几个标签,也不要糊成一团。 */
const labels = computed(() => {
  const ms = marks.value.filter(m => m.x > -40 && m.x < W + 40 && m.y > -40 && m.y < H + 40)
  const DIRS = [[1, 0], [-1, 0], [0, -1], [0, 1], [1, -1], [-1, -1], [1, 1], [-1, 1]]
  const dots = ms.map(m => ({ x0: m.x - 9, y0: m.y - 9, x1: m.x + 9, y1: m.y + 9 }))
  const boxes = []
  const hit = (a, b) => !(a.x1 < b.x0 - 3 || a.x0 > b.x1 + 3 || a.y1 < b.y0 - 2 || a.y0 > b.y1 + 2)
  const out = []

  for (const m of [...ms].sort((a, b) => a.pri - b.pri)) {
    const w = textWidth(m.label), h = FS * 1.08
    let placed = null
    for (let ring = 0; ring < 2 && !placed; ring++) {
      const gap = ring === 0 ? 10 : 24
      for (const [dxs, dys] of DIRS) {
        const anchor = dxs > 0 ? 'start' : (dxs < 0 ? 'end' : 'middle')
        const dx = dxs * gap
        const dy = dys === 0 ? FS * 0.34 : dys * (gap * 0.62) + (dys < 0 ? 0 : FS * 0.6)
        const x0 = anchor === 'start' ? m.x + dx : (anchor === 'end' ? m.x + dx - w : m.x - w / 2)
        const y0 = m.y + dy - h * 0.76
        const box = { x0: x0 - 4, y0: y0 - 2, x1: x0 + w + 4, y1: y0 + h + 2 }
        if (box.x0 < 3 || box.x1 > W - 3 || box.y0 < 3 || box.y1 > H - 3) continue
        if (boxes.some(b => hit(box, b))) continue
        if (dots.some(d => hit(box, d))) continue
        boxes.push(box)
        placed = {
          anchor,
          tx: anchor === 'middle' ? m.x : m.x + dx,
          ty: m.y + dy,
          box,
          lead: ring === 1,      // 推到外圈的才画引线
        }
        break
      }
    }
    if (!placed) continue
    const b = placed.box
    out.push({
      mark: m, text: m.label, anchor: placed.anchor,
      tx: placed.tx, ty: placed.ty,
      bx: b.x0, by: b.y0, bw: b.x1 - b.x0, bh: b.y1 - b.y0,
      lead: placed.lead,
      mx: m.x, my: m.y,
      lx: Math.max(b.x0, Math.min(m.x, b.x1)),
      ly: Math.max(b.y0, Math.min(m.y, b.y1)),
    })
  }
  return out
})

/* ---------- 详情 ---------- */

function describe(p) {
  activeStopId.value = p.id
  return {
    ...p,
    photo: photoUrl(p.photoSha),
    mapUrl: mapUrl({ lat: p.lat, lng: p.lng, name: p.t }),
  }
}
function openStop(p) {
  snapshotAccent()
  editing.value = false
  uploadErr.value = ''
  detail.value = describe(p)
}
function open(m) {
  if (suppressClick) return          // 刚拖完地图,不要顺手弹窗
  if (m?.stops?.length) openStop(m.stops[0])
}

const siblings = computed(() => {
  const d = detail.value
  if (!d) return []
  return marks.value.find(m => m.stops.some(s => s.id === d.id))?.stops || []
})

/* ---------- 编辑:介绍与照片 ---------- */

const editing = ref(false)
const draft = ref('')
const saving = ref(false)
const uploadErr = ref('')
const fileRef = ref(null)

function startEdit() {
  draft.value = detail.value?.desc || ''
  editing.value = true
}

/** 把改动写回当天的 detail 并 PATCH。
 *  这里直接改 props.days 里那个 detail 对象——它就是父组件 days 里的同一个
 *  对象,改完地图和右侧详情同时更新,不用把事件一层层往上传。 */
async function persist(patch) {
  const d = props.days.find(x => x.day_no === detail.value.dayNo)
  const stop = d?.detail?.stops?.[detail.value.si]
  if (!stop) return false
  Object.assign(stop, patch)
  const { default: api } = await import('@/api')
  await api.patch(`/api/trips/${props.tripId}/days/${d.day_no}`, { detail: d.detail })
  detail.value = describe({ ...detail.value, ...patch, photoSha: stop.photo || '' })
  emit('changed')
  return true
}

async function saveDesc() {
  saving.value = true
  uploadErr.value = ''
  try {
    await persist({ desc: draft.value.trim() })
    editing.value = false
  } catch (e) {
    uploadErr.value = e?.response?.data?.error || '保存失败'
  } finally {
    saving.value = false
  }
}

/** 上传前先在浏览器里缩到 1280px 的 JPEG:原图动辄 5MB,
 *  服务端单请求上限 8MB,而且这张图只是弹窗里的一张配图。 */
async function shrink(file, max = 1280, quality = 0.82) {
  const bmp = await createImageBitmap(file)
  const k = Math.min(1, max / Math.max(bmp.width, bmp.height))
  const w = Math.round(bmp.width * k), h = Math.round(bmp.height * k)
  const c = document.createElement('canvas')
  c.width = w; c.height = h
  c.getContext('2d').drawImage(bmp, 0, 0, w, h)
  bmp.close?.()
  return c.toDataURL('image/jpeg', quality)
}

async function onPickPhoto(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  saving.value = true
  uploadErr.value = ''
  try {
    const dataUrl = await shrink(file)
    const { default: api } = await import('@/api')
    const res = await api.post(`/api/trips/${props.tripId}/photos`, { image: dataUrl })
    await persist({ photo: res.data.sha256 })
  } catch (err) {
    uploadErr.value = err?.response?.data?.error || '上传失败'
  } finally {
    saving.value = false
  }
}

async function removePhoto() {
  saving.value = true
  try {
    await persist({ photo: '' })
  } finally {
    saving.value = false
  }
}

/* ---------- 缩放 / 平移 ---------- */

const MIN_ZOOM = 0.35, MAX_ZOOM = 8

function resetView() { zoom.value = 1; panX.value = 0; panY.value = 0 }

function onWheel(e) {
  const next = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom.value * (e.deltaY < 0 ? 1.15 : 1 / 1.15)))
  if (next === zoom.value) return
  // 以指针为锚点缩放,手感更自然
  const r = svgRef.value.getBoundingClientRect()
  const mx = (e.clientX - r.left) / r.width * W - W / 2
  const my = (e.clientY - r.top) / r.height * H - H / 2
  const k = next / zoom.value
  panX.value = mx - (mx - panX.value) * k
  panY.value = my - (my - panY.value) * k
  zoom.value = next
  if (next === 1) { panX.value = 0; panY.value = 0 }
}

let drag = null
let suppressClick = false

function onDown(e) {
  drag = { x: e.clientX, y: e.clientY, px: panX.value, py: panY.value, moved: false }
  svgRef.value.setPointerCapture?.(e.pointerId)
}
function onMove(e) {
  if (!drag) return
  const r = svgRef.value.getBoundingClientRect()
  const dx = (e.clientX - drag.x) / r.width * W
  const dy = (e.clientY - drag.y) / r.height * H
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) drag.moved = true
  panX.value = drag.px + dx
  panY.value = drag.py + dy
}
function onUp() {
  suppressClick = !!drag?.moved
  drag = null
  if (suppressClick) setTimeout(() => { suppressClick = false }, 0)
}
</script>

<style scoped>
.tmap { position: relative; }
.tmap-head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
.tmap-title { font-size: 12px; font-weight: 800; letter-spacing: .08em; color: var(--trip-ink-2, var(--color-text-muted)); }
.tmap-tools { display: flex; align-items: center; gap: 8px; }
.tmap-hint { font-size: 11px; color: var(--color-text-muted); }
.tmap-btn {
  appearance: none; border: 1px solid var(--color-border-light); background: var(--color-surface);
  color: var(--color-text-muted); font: inherit; font-size: 11px;
  padding: 2px 10px; border-radius: 999px; cursor: pointer;
}
.tmap-btn:disabled { opacity: .45; cursor: default; }

.tmap-svg {
  width: 100%; height: auto; display: block;
  /* 容器把高度压扁时 SVG 会按 viewBox 等比留白，背景必须和海面同色，
     否则两侧会露出卡片底色，看上去像地图糊了一块。 */
  background: var(--trip-accent-weak, #dce7ea);
  border-radius: 12px;
  border: 1px solid var(--trip-line, var(--color-border-light));
  touch-action: none; cursor: grab;
}
.tmap-svg:active { cursor: grabbing; }

.tmap-sea { fill: var(--trip-accent-weak, #dce7ea); }
.tmap-land {
  fill: var(--color-surface, #fff);
  stroke: color-mix(in srgb, var(--trip-accent, #2B6A80) 34%, transparent);
  stroke-width: 1; stroke-linejoin: round;
}

.tmap-leg {
  fill: none;
  stroke: var(--trip-accent, var(--color-primary));
  stroke-width: 2.2; stroke-linecap: round; opacity: .9;
}
.tmap-leg.sea { stroke-dasharray: 2.5 4; }
.tmap-leg.air { stroke-width: 1.5; stroke-dasharray: 7 5; opacity: .62; }

.tmap-lead { stroke: var(--color-text-muted); stroke-width: 1; opacity: .5; }

.tmap-mark { cursor: pointer; }
.tmap-ring { fill: var(--color-surface, #fff); }
.tmap-dot { fill: var(--trip-accent, var(--color-primary)); }
.tmap-dot.first { fill: #1d2b32; }
.tmap-dot.last { fill: #3C8C6E; }
.tmap-hit { fill: transparent; }
.tmap-mark:focus-visible { outline: none; }
.tmap-mark:focus-visible .tmap-ring { stroke: var(--trip-accent); stroke-width: 2; }
.tmap-mark:hover .tmap-dot, .tmap-mark.on .tmap-dot { fill: #b4562f; }
.tmap-badge { fill: var(--trip-accent, var(--color-primary)); stroke: var(--color-surface); stroke-width: 1.2; }
.tmap-badge-t { font-size: 7.8px; font-weight: 700; fill: #fff; text-anchor: middle; }

.tmap-label { cursor: pointer; }
.tmap-chip { fill: color-mix(in srgb, var(--color-surface, #fff) 92%, transparent); }
.tmap-chip-t { font-size: 11.5px; font-weight: 500; fill: var(--color-text-strong, #2A3D45); }

.tmap-legend {
  display: flex; flex-wrap: wrap; gap: 12px; margin-top: 8px;
  font-size: 11px; color: var(--color-text-muted);
}
.tmap-legend span { display: inline-flex; align-items: center; gap: 5px; }
.lg { width: 16px; height: 0; border-top: 2px solid var(--trip-accent, var(--color-primary)); display: inline-block; }
.lg-air { border-top-style: dashed; opacity: .6; }
.lg-sea { border-top-style: dotted; }
.dotl { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dotl.start { background: #1d2b32; }
.dotl.end { background: #3C8C6E; }

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
.tmap-li-dot.air { border-style: dashed; }
.tmap-li-dot.sea { border-width: 2.5px; }
.tmap-li.on .tmap-li-dot { background: #fff; border-color: #fff; }
.tmap-li-day { font-size: 10px; opacity: .65; font-variant-numeric: tabular-nums; }

.tmap-empty { padding: 14px 4px 2px; font-size: 12px; color: var(--color-text-muted); }

@media (max-width: 768px) {
  .tmap-hint { display: none; }
}
</style>

<style>
/* 详情弹窗 teleport 到 body,不能用 scoped */
.spot-mask {
  position: fixed; inset: 0; z-index: 3000;
  background: rgba(20, 26, 30, .52);
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
  animation: spot-fade .14s ease;
}
@keyframes spot-fade { from { opacity: 0 } }
.spot {
  position: relative;
  width: min(560px, 100%); max-height: min(86vh, 760px);
  overflow-y: auto;
  background: var(--color-surface, #fff);
  border-radius: 18px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, .3);
  animation: spot-rise .18s cubic-bezier(.2, .8, .3, 1);
}
@keyframes spot-rise { from { opacity: 0; transform: translateY(14px) scale(.98) } }
.spot-x {
  position: absolute; right: 10px; top: 10px; z-index: 2;
  width: 30px; height: 30px; border: 0; border-radius: 50%;
  background: rgba(255, 255, 255, .82); color: #333;
  font-size: 19px; line-height: 1; cursor: pointer;
}
.spot-photo { position: relative; height: 190px; background: var(--trip-accent-weak, #e3ebee); }
.spot-photo img { width: 100%; height: 100%; object-fit: cover; display: block; }
.spot-photo.empty { height: 116px; }
.spot-photo-ph {
  height: 100%; display: grid; place-items: center;
  font-size: 46px; font-weight: 900; opacity: .28;
  color: var(--trip-accent-ink, #2A3D45);
}
.spot-body { padding: 16px 20px 22px; }
.spot-top { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.spot-day {
  font-size: 11px; font-weight: 800; letter-spacing: .05em; color: #fff;
  background: var(--trip-accent, #2B6A80); padding: 2px 9px; border-radius: 999px;
}
.spot-date, .spot-tag { font-size: 11px; color: var(--color-text-muted); }
.spot-t { margin: 8px 0 0; font-size: 21px; font-weight: 900; color: var(--color-text-strong); }
.spot-meta { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 4px; font-size: 12px; color: var(--color-text-muted); }
.spot-desc { margin: 12px 0 0; font-size: 13.5px; line-height: 1.75; color: var(--color-text); white-space: pre-wrap; }
.spot-desc-none { color: var(--color-text-muted); }
.spot-edit {
  width: 100%; margin-top: 12px; box-sizing: border-box;
  border: 1px solid var(--color-border-light, #e3ddd0); border-radius: 10px;
  padding: 9px 11px; font: inherit; font-size: 13.5px; line-height: 1.7;
  resize: vertical; background: var(--color-surface); color: var(--color-text);
}
.spot-edit:focus { outline: none; border-color: var(--trip-accent, var(--color-primary)); }
.spot-edit-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.spot-b {
  appearance: none; border: 1px solid var(--color-border-light); background: var(--color-surface);
  color: var(--color-text); font: inherit; font-size: 12.5px;
  padding: 4px 14px; border-radius: 999px; cursor: pointer;
}
.spot-b.primary {
  background: var(--trip-accent, var(--color-primary));
  border-color: var(--trip-accent, var(--color-primary)); color: #fff; font-weight: 700;
}
.spot-edit-b {
  appearance: none; border: 0; background: none; cursor: pointer; padding: 4px 0;
  font: inherit; font-size: 12px; color: var(--trip-accent, var(--color-primary));
}
.spot-err { margin: 8px 0 0; font-size: 12px; color: var(--color-error, #e05a5a); }
.spot-photo-act {
  position: absolute; left: 10px; bottom: 10px; display: flex; gap: 6px;
}
.spot-photo-act button {
  appearance: none; border: 0; cursor: pointer; font: inherit; font-size: 11.5px;
  background: rgba(255, 255, 255, .86); color: #2A3D45;
  padding: 3px 10px; border-radius: 999px;
}
.spot-photo-act button:disabled { opacity: .55; cursor: default; }
.spot-tips { margin-top: 14px; }
.spot-tips h4 {
  margin: 0 0 4px; font-size: 11px; font-weight: 800; letter-spacing: .08em;
  color: var(--trip-accent, var(--color-primary));
}
.spot-tips ul { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.7; }
.spot-sib { margin-top: 14px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 12px; color: var(--color-text-muted); }
.spot-sib-b {
  appearance: none; border: 1px solid var(--color-border-light); background: var(--color-surface);
  font: inherit; font-size: 12px; padding: 2px 9px; border-radius: 999px; cursor: pointer;
  color: var(--color-text);
}
.spot-sib-b.on { background: var(--trip-accent, var(--color-primary)); border-color: var(--trip-accent); color: #fff; }
.spot-map {
  display: inline-block; margin-top: 16px; font-size: 12.5px; font-weight: 700;
  text-decoration: none; color: var(--trip-accent, var(--color-primary));
  border: 1px solid var(--trip-accent, var(--color-primary));
  border-radius: 999px; padding: 4px 13px;
}
.spot-map:hover { background: var(--trip-accent, var(--color-primary)); color: #fff; }

@media (max-width: 560px) {
  .spot-mask { padding: 0; align-items: flex-end; }
  .spot { width: 100%; max-height: 92vh; border-radius: 18px 18px 0 0; }
  .spot-photo { height: 160px; }
}
</style>
