<!-- components/TripMap.vue — 行程地图:高德底图 + 曲线航段 + 可点停留点

     用真实底图而不是自己画海岸线:街道、地名、POI 这些周边信息是自己画
     拿不到的。高德栅格瓦片的地名全球都是中文,国内加载也快。

     两件必须注意的事:
       1. 高德瓦片是 GCJ-02 坐标,行程里存的是 WGS-84。境内直接画会偏几百米,
          所以画之前统一过一遍 wgs2gcj(境外两者一致,函数会原样返回)。
       2. 整站 CSP 是 default-src 'self',瓦片域名要在 img-src 里放行。
          只放图片源,不引第三方脚本。 -->
<template>
  <div class="tmap">
    <div class="tmap-head">
      <span class="tmap-title">{{ title }}</span>
      <div class="tmap-tools">
        <button
          v-for="l in LAYERS"
          :key="l.key"
          type="button"
          class="tmap-btn"
          :class="{ on: layer === l.key }"
          @click="setLayer(l.key)"
        >{{ l.label }}</button>
        <button type="button" class="tmap-btn" @click="fitAll">复位</button>
      </div>
    </div>

    <div ref="mapEl" class="tmap-canvas"></div>

    <div class="tmap-legend">
      <span v-if="hasAir"><i class="lg lg-air"></i>飞行</span>
      <span v-if="hasSea"><i class="lg lg-sea"></i>航船</span>
      <span><i class="lg lg-road"></i>陆路</span>
      <span><i class="dotl start"></i>起点</span>
      <span><i class="dotl end"></i>终点</span>
    </div>

    <!-- 停留点列表:低缩放下点会叠在一起,列表保证每个点都可达,
         也给键盘 / 读屏用户一条路径。 -->
    <ul v-if="points.length" class="tmap-list">
      <li v-for="p in points" :key="p.id">
        <button
          type="button"
          class="tmap-li"
          :class="{ on: activeStopId === p.id }"
          @click="focusStop(p)"
        >
          <span class="tmap-li-dot" :class="{ air: p.air, sea: p.sea }"></span>
          {{ p.t }}
          <span class="tmap-li-day">D{{ p.dayNo }}</span>
        </button>
      </li>
    </ul>
    <div v-else-if="!unlocated.length" class="tmap-empty">这段行程还没有标记地点。</div>

    <!-- 没有坐标的地点。定位不接地理编码服务:模型本来就知道大部分地名在哪,
         而且结果必须过人眼——所以它给的是个可以拖的草稿点,不是直接落库。 -->
    <div v-if="canEdit && unlocated.length" class="tmap-un">
      <div class="tmap-un-h">还有 {{ unlocated.length }} 个地点没有位置</div>
      <ul class="tmap-un-l">
        <li v-for="u in unlocated" :key="u.key">
          <span class="tmap-un-n">{{ u.t }}</span>
          <span class="tmap-un-d">D{{ u.dayNo }}</span>
          <button
            type="button"
            class="tmap-btn"
            :disabled="geoBusy(u) || !!geoDraft"
            @click="locate(u)"
          >
            <span v-if="geoBusy(u)" class="spot-spin" aria-hidden="true"></span>
            {{ geoBusy(u) ? `${geoSecs(u)}s` : '✨ 定位' }}
          </button>
        </li>
      </ul>
      <p v-if="geoErr" class="tmap-un-e">{{ geoErr }}</p>
    </div>

    <!-- 草稿点的确认条。AI 记错坐标是常事,所以一律先看一眼再存 -->
    <div v-if="geoDraft" class="tmap-draft">
      <div class="tmap-draft-t">
        <b>{{ geoDraft.t }}</b>
        <span v-if="geoDraft.place" class="tmap-draft-p">AI 认为这是:{{ geoDraft.place }}</span>
        <span v-if="!geoDraft.sure" class="tmap-draft-w">模型说它不太确定,务必核对</span>
      </div>
      <p class="tmap-draft-h">地图上那个空心点就是它。位置不对可以直接拖动,再保存。</p>
      <div class="tmap-draft-b">
        <span class="tmap-draft-c">{{ geoDraft.lat.toFixed(4) }}, {{ geoDraft.lng.toFixed(4) }}</span>
        <span class="tmap-un-sp"></span>
        <button type="button" class="tmap-btn" @click="dropDraft">不对,丢弃</button>
        <button type="button" class="tmap-btn on" :disabled="savingGeo" @click="keepDraft">
          {{ savingGeo ? '保存中…' : '就是这儿' }}
        </button>
      </div>
    </div>

    <!-- 景点详情:大窗口 -->
    <teleport to="body">
      <div v-if="detail" class="spot-mask" @click.self="detail = null">
        <div class="spot" :style="accentStyle" role="dialog" aria-modal="true">
          <button class="spot-x" aria-label="关闭" @click="detail = null">×</button>

          <div class="spot-photo" :class="{ empty: !detail.cover }">
            <img v-if="detail.cover" :src="detail.cover" :alt="detail.t" />
            <div v-else class="spot-photo-ph">
              <span>{{ detail.t.slice(0, 1) }}</span>
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
                <button
                  type="button"
                  class="spot-b spot-ai"
                  :disabled="descAi.running || saving"
                  @click="genDesc"
                >
                  <span v-if="descAi.running" class="spot-spin" aria-hidden="true"></span>
                  {{ descAi.running ? `生成中… ${descSecs}s` : '✨ 让 AI 写' }}
                </button>
                <span class="spot-gap"></span>
                <button type="button" class="spot-b" @click="editing = false">取消</button>
                <button type="button" class="spot-b primary" :disabled="saving" @click="saveDesc">
                  {{ saving ? '保存中…' : '保存' }}
                </button>
              </div>
            </template>
            <template v-else>
              <p v-if="detail.desc" class="spot-desc">{{ detail.desc }}</p>
              <p v-else class="spot-desc spot-desc-none">这个点还没有写介绍。</p>
              <div v-if="canEdit" class="spot-edit-row">
                <button type="button" class="spot-edit-b" @click="startEdit">
                  ✎ {{ detail.desc ? '改介绍' : '写介绍' }}
                </button>
                <button
                  type="button"
                  class="spot-edit-b"
                  :disabled="descAi.running"
                  @click="genDesc"
                >
                  <span v-if="descAi.running" class="spot-spin" aria-hidden="true"></span>
                  {{ descAi.running ? `生成中… ${descSecs}s` : '✨ 让 AI 写' }}
                </button>
              </div>
            </template>

            <p v-if="uploadErr || descAi.error" class="spot-err">
              {{ uploadErr || descAi.error }}
            </p>
            <p v-else-if="descAi.running" class="spot-dim-note">
              AI 正在写,要十几秒。这期间关掉弹窗也不影响,写完回来还在。
            </p>

            <div v-if="canEdit || detail.photos.length" class="spot-ps">
              <TripPhotoStrip
                :photos="detail.photos"
                :can-edit="canEdit"
                :trip-id="tripId"
                :share-token="shareToken"
                label="照片"
                @change="savePhotos"
              />
            </div>

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
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import TripPhotoStrip from '@/components/TripPhotoStrip.vue'
import { mapUrl } from '@/utils/maplink'
import { wgs2gcj, gcj2wgs } from '@/utils/gcj02'
import { photoList, photoUrl } from '@/utils/tripPhotos'
import { aiState, aiElapsed, runAiBlock, clearAiBlock } from '@/utils/aiJobs'

const props = defineProps({
  // [{ day_no, date, route, detail:{ stops:[{t,dur,lat,lng,air,sea,desc,photo}], todo, cam, warn } }]
  days: { type: Array, default: () => [] },
  title: { type: String, default: '全程路线' },
  // 给了 tripId 才能改介绍 / 传照片;公开分享页只给 shareToken,永远只读
  tripId: { type: Number, default: 0 },
  shareToken: { type: String, default: '' },
})
const emit = defineEmits(['changed'])

const canEdit = computed(() => !!props.tripId && !props.shareToken)

/* ---------- 底图 ---------- */

// 卫星图没有地名,叠一层高德的注记层上去
const AMAP_LABEL = 'https://webst0{s}.is.autonavi.com/appmaptile?style=8&x={x}&y={y}&z={z}'

/** 两套底图的坐标系不一样,切图层时点和线都要跟着换算:
 *  高德是 GCJ-02(火星坐标),OSM 是 WGS-84。混着用,境内会整体偏几百米。
 *
 *  maxNativeZoom 很关键:超过瓦片实际存在的层级,Leaflet 默认会去请求
 *  根本不存在的瓦片,画面就整片空白;设了它就改成把最后一级放大显示。
 *  minZoom 同理——缩得太远高德那边也没有瓦片。 */
const LAYERS = [
  {
    key: 'amap', label: '高德', datum: 'gcj02',
    url: 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
    opts: { subdomains: '1234', minZoom: 3, maxZoom: 19, maxNativeZoom: 18, attribution: '© 高德地图' },
  },
  {
    // 高德的境外数据很薄,放大基本看不到街道;国际底图用 OSM 补上
    key: 'osm', label: '国际', datum: 'wgs84',
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    opts: { minZoom: 2, maxZoom: 19, maxNativeZoom: 19, attribution: '© OpenStreetMap' },
  },
  {
    key: 'sat', label: '卫星', datum: 'gcj02',
    url: 'https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}',
    opts: { subdomains: '1234', minZoom: 3, maxZoom: 19, maxNativeZoom: 18, attribution: '© 高德地图' },
    labels: AMAP_LABEL,
  },
]
const LAYER_KEY = 'trip:maplayer'
const layer = ref('amap')
const layerDef = computed(() => LAYERS.find(l => l.key === layer.value) || LAYERS[0])

/* ---------- 取点 ---------- */

const mapEl = ref(null)
const detail = ref(null)
const activeStopId = ref(null)

let map = null
let baseLayer = null
let labelLayer = null
let routeGroup = null
let markerGroup = null
let markerById = new Map()
let litId = null
let ro = null

/** 收集所有**带坐标**的地点,按天顺序;顺带把提到这个地名的贴士配对上去——
 *  静态行程页里介绍是散在 todo / cam 里的,不配对的话点开只会看到一句
 *  "还没有介绍"。
 *
 *  没坐标的地点不在这儿(地图画不了),但它在当天详情的地点列表里。 */
const points = computed(() => {
  const out = []
  for (const d of props.days) {
    const det = d.detail || {}
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
        lat, lng,                 // 一律存 WGS-84;画到哪套坐标系由 coord() 决定
        air: !!st.air, sea: !!st.sea,
        desc: st.desc || st.note || '',
        photos: photoList(st),
        dur: st.dur || '',
        tips: tipPool.filter(x => typeof x === 'string' && x.includes(name)),
        dayNo: d.day_no,
        date: d.date || '',
        route: d.route || '',
      })
    }
  }
  return out
})

/** 没有坐标的地点:它们不在地图上,但要能从这儿给它们定位。 */
const unlocated = computed(() => {
  const out = []
  for (const d of props.days) {
    const stops = d.detail?.stops || []
    for (let si = 0; si < stops.length; si++) {
      const st = stops[si]
      if (!st || !st.t) continue
      if (isFinite(Number(st.lat)) && isFinite(Number(st.lng))) continue
      out.push({ key: `${d.day_no}-${si}`, t: st.t, dayNo: d.day_no, si })
    }
  }
  return out
})

/** 按当前底图的坐标系换算出要画的位置。 */
function coord(p) {
  return layerDef.value.datum === 'gcj02' ? wgs2gcj(p.lat, p.lng) : [p.lat, p.lng]
}

const hasAir = computed(() => points.value.some(p => p.air))
const hasSea = computed(() => points.value.some(p => p.sea))

/** 复位视野用的范围。
 *
 *  直接框住全部点有个很难看的后果:一条「上海 ✈ 赫尔辛基」的长途航段会把
 *  视野拉到半个欧亚大陆,真正要看的北欧缩成一小团。所以先算中间 90% 的点的
 *  范围,只有当它明显更小(确实存在远端离群点)才用它;点少或分布均匀时
 *  两者几乎一样。被排除的点照画,缩小一点就能看到。 */
function fitBounds() {
  const pts = points.value
  if (!pts.length) return null
  const cs = pts.map(coord)
  const lats = cs.map(c => c[0]).sort((a, b) => a - b)
  const lngs = cs.map(c => c[1]).sort((a, b) => a - b)
  const at = (arr, t) => arr[Math.max(0, Math.min(arr.length - 1, Math.round((arr.length - 1) * t)))]
  const full = [[lats[0], lngs[0]], [lats[lats.length - 1], lngs[lngs.length - 1]]]
  if (pts.length < 8) return L.latLngBounds(full)
  const core = [[at(lats, 0.05), at(lngs, 0.05)], [at(lats, 0.95), at(lngs, 0.95)]]
  const area = (b) => Math.max(b[1][0] - b[0][0], 1e-6) * Math.max(b[1][1] - b[0][1], 1e-6)
  return L.latLngBounds(area(core) < area(full) * 0.5 ? core : full)
}

/* ---------- 画 ---------- */

/** 两点之间的弧线:直线看着像网络拓扑图,弧线才像航线。
 *  控制点沿弦的垂线外推,飞行段拱得更明显。 */
function arc(a, b, bend, segments = 28) {
  const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
  const k = Math.max(Math.cos(mid[0] * Math.PI / 180), 0.1)
  const dx = (b[1] - a[1]) * k, dy = b[0] - a[0]
  const cp = [mid[0] + dx * bend, mid[1] - dy * bend / k]
  const out = []
  const N = segments
  for (let i = 0; i <= N; i++) {
    const t = i / N, u = 1 - t
    out.push([
      u * u * a[0] + 2 * u * t * cp[0] + t * t * b[0],
      u * u * a[1] + 2 * u * t * cp[1] + t * t * b[1],
    ])
  }
  return out
}

const hasHover = typeof window !== 'undefined'
  && window.matchMedia?.('(hover: hover)').matches !== false


function accentColor() {
  const el = mapEl.value
  if (!el) return '#2B6A80'
  return (getComputedStyle(el).getPropertyValue('--trip-accent') || '').trim() || '#2B6A80'
}

function draw() {
  if (!map) return
  routeGroup.clearLayers()
  markerGroup.clearLayers()
  markerById = new Map()

  const ps = points.value
  const color = accentColor()

  for (let i = 1; i < ps.length; i++) {
    const a = coord(ps[i - 1])
    const b = coord(ps[i])
    if (a[0] === b[0] && a[1] === b[1]) continue
    const air = ps[i].air, sea = ps[i].sea
    // 采样数按航段长短来:同城两个点之间画 28 段纯属浪费,
    // 一趟行程几十段加起来就是上千个点。
    const span = Math.hypot(a[0] - b[0], (a[1] - b[1]) * 0.6)
    const segs = span < 0.05 ? 2 : (span < 0.5 ? 8 : (span < 3 ? 16 : 28))
    L.polyline(arc(a, b, air ? 0.17 : 0.09, segs), {
      color: air ? '#8A9EA3' : color,
      weight: air ? 2 : 3,
      opacity: air ? 0.75 : 0.9,
      dashArray: air ? '8 6' : (sea ? '3 6' : null),
      lineCap: 'round',
      interactive: false,
    }).addTo(routeGroup)
  }

  const pins = []
  ps.forEach((p, i) => {
    const first = i === 0, last = i === ps.length - 1
    const m = L.circleMarker(coord(p), {
      radius: first || last ? 7 : 6,
      fillColor: first ? '#1d2b32' : (last ? '#3C8C6E' : color),
      fillOpacity: 1,
      color: '#fff',              // 白圈,压在底图上才看得清
      weight: 2.5,
      interactive: true,
      bubblingMouseEvents: false,
    })
    m.on('click', () => openStop(p))
    // 触屏设备没有 hover:浮动名字根本出不来,却要为每个点多挂三组监听,
    // 六七十个点加起来不是小数目。只在有指针设备时才绑。
    if (hasHover) {
      m.bindTooltip(p.t, { direction: 'top', offset: [0, -8] })
      m.on('mouseover', () => m.setStyle({ weight: 3.5 }))
      m.on('mouseout', () => m.setStyle({ weight: 2.5 }))
    }
    m.options.__base = m.options.fillColor     // 高亮后要还原
    pins.push(m)
    markerById.set(p.id, m)
  })
  // 一次性加进去:逐个 addTo 会触发多次布局
  L.layerGroup(pins).addTo(markerGroup)
  litId = null
}

function setLayer(key) {
  const prev = layerDef.value
  const next = LAYERS.find(l => l.key === key) || LAYERS[0]
  layer.value = next.key
  try { localStorage.setItem(LAYER_KEY, next.key) } catch { /* 隐私模式下会抛 */ }
  if (!map) return

  // 换坐标系时把当前中心也换过去,否则一切图整幅跳几百米
  let center = null
  if (map._loaded && prev.datum !== next.datum) {
    const c = map.getCenter()
    center = next.datum === 'gcj02'
      ? wgs2gcj(c.lat, c.lng)
      : gcj2wgs(c.lat, c.lng)
  }

  if (baseLayer) map.removeLayer(baseLayer)
  if (labelLayer) { map.removeLayer(labelLayer); labelLayer = null }
  baseLayer = L.tileLayer(next.url, next.opts).addTo(map)
  if (next.labels) {
    labelLayer = L.tileLayer(next.labels, next.opts).addTo(map)
  }
  baseLayer.bringToBack()

  if (map._loaded) {
    draw()
    if (center) map.setView(center, map.getZoom(), { animate: false })
  }
}

function fitAll() {
  const b = fitBounds()
  if (b && map) map.fitBounds(b, { padding: [36, 36] })
}

/** 选默认底图:行程主要在境外就用 OSM——高德境外几乎没有街道数据,
 *  放大只剩一片底色。用户手动切过就一直听用户的。 */
function pickDefaultLayer() {
  let saved = null
  try { saved = localStorage.getItem(LAYER_KEY) } catch { /* 隐私模式 */ }
  if (saved && LAYERS.some(l => l.key === saved)) return saved
  const pts = points.value
  if (!pts.length) return 'amap'
  const inChina = pts.filter(p =>
    p.lng > 72 && p.lng < 138 && p.lat > 0.8 && p.lat < 56).length
  return inChina * 2 >= pts.length ? 'amap' : 'osm'
}

onMounted(() => {
  layer.value = pickDefaultLayer()
  map = L.map(mapEl.value, {
    zoomControl: true,
    attributionControl: true,
    scrollWheelZoom: true,
    worldCopyJump: true,
    // 画布渲染:一趟行程六七十个点,用 DOM 标记就是六七十个元素,
    // 切换行程时全删全建,手机上肉眼可见地卡。画布下它们都落在一张 canvas 上。
    preferCanvas: true,
  })
  routeGroup = L.layerGroup().addTo(map)
  markerGroup = L.layerGroup().addTo(map)
  setLayer(layer.value)
  draw()
  fitAll()
  // 地图装在切换面板 / 抽屉里,显示出来时尺寸才定下来,必须重算
  ro = new ResizeObserver(() => map && map.invalidateSize())
  ro.observe(mapEl.value)
  // 定位结果在模块级 store 里异步回来,这里轮一下。只有还有没定位的点
  // 才有必要轮,定完就自然停了(unlocated 空 → absorbGeo 什么都不做)
  geoTimer = setInterval(absorbGeo, 800)
})

onBeforeUnmount(() => {
  clearInterval(geoTimer)
  hideDraft()
  if (redrawHandle) cancelAnimationFrame(redrawHandle)
  ro?.disconnect()
  map?.remove()
  map = null
})

/** 换行程时先让标题、日历这些便宜的东西画出来,地图下一帧再重绘。
 *  否则一次点击要同步做完几十个图层,手机上就是"点了卡一下"。 */
let redrawHandle = 0
watch(points, () => {
  if (redrawHandle) cancelAnimationFrame(redrawHandle)
  redrawHandle = requestAnimationFrame(() => {
    redrawHandle = 0
    draw()
    fitAll()
  })
})

/* ---------- 详情 ---------- */

// 弹窗 teleport 到 body,拿不到外层 .travel-page 上的主题色变量,
// 打开时从组件所在位置把它们读出来带过去。
const ACCENT_VARS = ['--trip-accent', '--trip-accent-weak', '--trip-accent-ink']
const accentStyle = ref({})
function snapshotAccent() {
  const el = mapEl.value
  if (!el) return
  const cs = getComputedStyle(el)
  const out = {}
  for (const k of ACCENT_VARS) {
    const v = cs.getPropertyValue(k).trim()
    if (v) out[k] = v
  }
  accentStyle.value = out
}

function describe(p) {
  activeStopId.value = p.id
  const ctx = { tripId: props.tripId, shareToken: props.shareToken }
  return {
    ...p,
    cover: photoUrl(ctx, p.photos[0]),
    mapUrl: mapUrl({ lat: p.lat, lng: p.lng, name: p.t }),
  }
}

function openStop(p) {
  snapshotAccent()
  editing.value = false
  uploadErr.value = ''
  detail.value = describe(p)
  absorbDesc()          // 这个点之前发起过生成、结果已经回来了的话,直接接上
}

/** 选中的那个点高亮。画布渲染没有 CSS class 可用,直接改样式。 */
watch(activeStopId, (id) => {
  const prev = litId && markerById.get(litId)
  if (prev) prev.setStyle({ fillColor: prev.options.__base, weight: 2.5 })
  const cur = id && markerById.get(id)
  if (cur) {
    if (cur.options.__base === undefined) cur.options.__base = cur.options.fillColor
    cur.setStyle({ fillColor: '#b4562f', weight: 3.5 })
  }
  litId = id
})

/* ---------- AI 定位 ---------- */
// 为什么不接地理编码服务:模型本来就知道大部分地名在哪,多一个外部依赖
// (还要申请 key、配额、再往 CSP 里放一个域名)不划算。代价是它会记错,
// 所以结果一律当草稿:画一个可以拖的空心点,人确认了才落库。

const geoDraft = ref(null)          // { t, dayNo, si, lat, lng, place, sure }
const savingGeo = ref(false)
const geoErr = ref('')
let draftMarker = null

function geoKey(u) { return `spot_geo:${props.tripId}:${u.dayNo}:${u.si}` }
function geoBusy(u) { return aiState(geoKey(u)).running }
function geoSecs(u) { return aiElapsed(geoKey(u)) }

async function locate(u) {
  geoErr.value = ''
  const day = props.days.find(x => x.day_no === u.dayNo)
  await runAiBlock(geoKey(u), `/api/trips/${props.tripId}/ai/block`, {
    kind: 'spot_geo',
    spot: u.t,
    day_no: u.dayNo,
    // 同名的地方靠当天路线消歧
    hint: day?.route ? `这一天的路线:${day.route}` : undefined,
    label: `定位「${u.t}」`,
  })
}

/** 轮询结果回来了就摆一个草稿点。 */
function absorbGeo() {
  for (const u of unlocated.value) {
    const st = aiState(geoKey(u))
    if (!st.result) continue
    const r = st.result
    clearAiBlock(geoKey(u))
    if (r.lat == null || r.lng == null) {
      geoErr.value = `AI 也说不准「${u.t}」在哪${r.place ? `(它猜是 ${r.place})` : ''}。`
                   + '可以把名字写全一点再试,比如带上城市。'
      return
    }
    geoDraft.value = { ...u, lat: r.lat, lng: r.lng, place: r.place || '', sure: !!r.sure }
    showDraft()
    return
  }
}
watch(unlocated, absorbGeo)
// 结果是异步回来的,轮一下:这几个 key 的状态都在模块级 store 里
let geoTimer = null

function showDraft() {
  if (!map || !geoDraft.value) return
  hideDraft()
  const at = coord(geoDraft.value)
  draftMarker = L.marker(at, {
    draggable: true,
    // 空心点:和已经定好的实心点区分开,一眼能看出这个还没存
    icon: L.divIcon({ className: 'tmap-draft-pin', html: '<i></i>',
                      iconSize: [18, 18], iconAnchor: [9, 9] }),
  }).addTo(map)
  draftMarker.on('dragend', () => {
    const ll = draftMarker.getLatLng()
    // 拖动拿到的是**当前底图**坐标系的值,存回去要换回 WGS-84
    const [lat, lng] = layerDef.value.datum === 'gcj02'
      ? gcj2wgs(ll.lat, ll.lng)
      : [ll.lat, ll.lng]
    geoDraft.value = { ...geoDraft.value, lat, lng }
  })
  map.flyTo(at, Math.max(map.getZoom(), 12), { duration: 0.6 })
}

function hideDraft() {
  if (draftMarker) {
    draftMarker.remove()
    draftMarker = null
  }
}

function dropDraft() {
  hideDraft()
  geoDraft.value = null
}

async function keepDraft() {
  const d = geoDraft.value
  if (!d) return
  savingGeo.value = true
  try {
    const day = props.days.find(x => x.day_no === d.dayNo)
    const stop = day?.detail?.stops?.[d.si]
    if (!stop) return
    stop.lat = Number(d.lat.toFixed(6))
    stop.lng = Number(d.lng.toFixed(6))
    const { default: api } = await import('@/api')
    await api.patch(`/api/trips/${props.tripId}/days/${day.day_no}`, { detail: day.detail })
    hideDraft()
    geoDraft.value = null
    emit('changed')
  } catch (e) {
    geoErr.value = e?.response?.data?.error || '保存失败,再试一次'
  } finally {
    savingGeo.value = false
  }
}

/** 列表点进来的:先把地图飞过去,再弹窗,不然不知道这个点在哪。 */
function focusStop(p) {
  if (map) map.flyTo(coord(p), Math.max(map.getZoom(), 10), { duration: 0.6 })
  openStop(p)
}

const siblings = computed(() => {
  const d = detail.value
  if (!d) return []
  // 同一天、离得很近(约 1km 内)的点,当作"这一带"
  return points.value.filter(p =>
    p.dayNo === d.dayNo &&
    Math.abs(p.lat - d.lat) < 0.012 &&
    Math.abs(p.lng - d.lng) < 0.02)
})

/* ---------- 编辑:介绍与照片 ---------- */

const editing = ref(false)
const draft = ref('')
const saving = ref(false)
const uploadErr = ref('')

function startEdit() {
  draft.value = detail.value?.desc || ''
  editing.value = true
}

/** AI 写的是**草稿**:填进编辑框,存不存由用户决定。
 *  直接写库会盖掉人家自己写的那段,不能这么干。
 *
 *  在途状态放模块级 store:弹窗关了、切到别的天再回来,进度和结果都还在。 */
const descKey = computed(() =>
  `spot_desc:${props.tripId}:${detail.value?.dayNo || 0}:${detail.value?.si ?? 0}`)
const descAi = computed(() => aiState(descKey.value))
const descSecs = computed(() => aiElapsed(descKey.value))

function absorbDesc() {
  const data = descAi.value.result
  if (!data?.text) return
  draft.value = data.text
  editing.value = true
  clearAiBlock(descKey.value)
}
watch(() => descAi.value.result, absorbDesc)

async function genDesc() {
  if (!canEdit.value || !detail.value) return
  uploadErr.value = ''
  if (!editing.value) { draft.value = detail.value.desc || ''; editing.value = true }
  await runAiBlock(descKey.value, `/api/trips/${props.tripId}/ai/block`, {
    kind: 'spot_desc',
    spot: detail.value.t,
    day_no: detail.value.dayNo,
  })
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
  detail.value = describe({ ...detail.value, ...patch, photos: photoList(stop) })
  emit('changed')
  return true
}

async function savePhotos(photos) {
  saving.value = true
  uploadErr.value = ''
  try {
    await persist({ photos, photo: undefined })   // 统一到数组,旧的单张字段清掉
  } catch (e) {
    uploadErr.value = e?.response?.data?.error || '保存失败'
  } finally {
    saving.value = false
  }
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

</script>

<style scoped>
.tmap { position: relative; }
.tmap-head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
.tmap-title { font-size: 12px; font-weight: 800; letter-spacing: .08em; color: var(--trip-ink-2, var(--color-text-muted)); }
.tmap-tools { display: flex; align-items: center; gap: 6px; }
.tmap-btn {
  appearance: none; border: 1px solid var(--color-border-light); background: var(--color-surface);
  color: var(--color-text-muted); font: inherit; font-size: 11px;
  padding: 2px 10px; border-radius: 999px; cursor: pointer;
}
.tmap-btn.on {
  background: var(--trip-accent, var(--color-primary));
  border-color: var(--trip-accent, var(--color-primary)); color: #fff;
}

.tmap-canvas {
  width: 100%;
  /* 手机上别让地图吃掉整屏:打开当天先看到的应该是行程,不是一张地图 */
  height: clamp(220px, 34vh, 520px);
  border-radius: 12px;
  border: 1px solid var(--trip-line, var(--color-border-light));
  background: var(--trip-accent-weak, #dce7ea);
  z-index: 0;                 /* 别盖住页面上的吸顶条 */
}

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

/* 没有坐标的地点 + 草稿点 */
.tmap-un { margin-top: 10px; padding: 8px 10px; border-radius: 10px;
  background: var(--color-surface-2, rgba(0,0,0,.04)); }
.tmap-un-h { font-size: 11.5px; color: var(--color-text-muted); margin-bottom: 6px; }
.tmap-un-l { list-style: none; margin: 0; padding: 0; display: flex;
  flex-direction: column; gap: 5px; }
.tmap-un-l li { display: flex; align-items: center; gap: 8px; font-size: 12.5px; }
.tmap-un-n { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tmap-un-d { font-size: 11px; color: var(--color-text-muted); flex: 0 0 auto; }
.tmap-un-e { margin: 8px 0 0; font-size: 11.5px; color: var(--color-error, #e05a5a); line-height: 1.6; }
.tmap-un-sp { flex: 1; }

.tmap-draft { margin-top: 10px; padding: 9px 11px; border-radius: 10px;
  border: 1px dashed var(--trip-accent, var(--color-primary)); }
.tmap-draft-t { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; font-size: 13px; }
.tmap-draft-p { font-size: 11.5px; color: var(--color-text-muted); }
.tmap-draft-w { font-size: 11.5px; color: var(--color-warning, #c9843a); }
.tmap-draft-h { margin: 5px 0 8px; font-size: 11.5px; color: var(--color-text-muted); line-height: 1.6; }
.tmap-draft-b { display: flex; align-items: center; gap: 8px; }
.tmap-draft-c { font-size: 11.5px; color: var(--color-text-muted); font-variant-numeric: tabular-nums; }
.tmap-empty { padding: 14px 4px 2px; font-size: 12px; color: var(--color-text-muted); }

@media (min-width: 900px) {
  .tmap-canvas { height: clamp(320px, 52vh, 520px); }
}
</style>

<style>
/* 草稿点。非 scoped:Leaflet 的 divIcon 是它自己 new 出来的元素,
   带不上 scoped 的 data 属性 */
.tmap-draft-pin i {
  display: block; width: 14px; height: 14px; margin: 2px; border-radius: 50%;
  background: rgba(255,255,255,.9); border: 3px solid #b4562f;
  box-shadow: 0 1px 4px rgba(0,0,0,.35); cursor: grab;
}
.tmap-draft-pin i:active { cursor: grabbing; }
</style>


<style>
/* Leaflet 的类名在组件外,加上 teleport 到 body 的弹窗,这一段不能 scoped */
.leaflet-container { font: inherit; }
.leaflet-container .leaflet-control-attribution { font-size: 10px; }
.leaflet-tooltip { font-size: 12px; padding: 2px 8px; }

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
.spot-dim-note { margin: 8px 0 0; font-size: 11.5px; color: var(--color-text-muted); }
.spot-edit {
  width: 100%; margin-top: 12px; box-sizing: border-box;
  border: 1px solid var(--color-border-light, #e3ddd0); border-radius: 10px;
  padding: 9px 11px; font: inherit; font-size: 13.5px; line-height: 1.7;
  resize: vertical; background: var(--color-surface); color: var(--color-text);
}
.spot-edit:focus { outline: none; border-color: var(--trip-accent, var(--color-primary)); }
.spot-edit-foot { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.spot-b {
  appearance: none; border: 1px solid var(--color-border-light); background: var(--color-surface);
  color: var(--color-text); font: inherit; font-size: 12.5px;
  padding: 4px 14px; border-radius: 999px; cursor: pointer;
}
.spot-b.primary {
  background: var(--trip-accent, var(--color-primary));
  border-color: var(--trip-accent, var(--color-primary)); color: #fff; font-weight: 700;
}
.spot-edit-row { display: flex; gap: 14px; }
.spot-edit-b {
  appearance: none; border: 0; background: none; cursor: pointer; padding: 4px 0;
  font: inherit; font-size: 12px; color: var(--trip-accent, var(--color-primary));
}
.spot-edit-b:disabled { opacity: .55; cursor: default; }
.spot-gap { flex: 1; }
.spot-ai { color: var(--trip-accent, var(--color-primary)); border-color: currentColor; }
.spot-err { margin: 8px 0 0; font-size: 12px; color: var(--color-error, #e05a5a); }
.spot-spin {
  display: inline-block; width: 9px; height: 9px; margin-right: 4px;
  vertical-align: -1px; border-radius: 50%;
  border: 2px solid currentColor; border-top-color: transparent;
  animation: spot-rot .7s linear infinite;
}
@keyframes spot-rot { to { transform: rotate(360deg); } }
.spot-ps { margin-top: 16px; }
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
