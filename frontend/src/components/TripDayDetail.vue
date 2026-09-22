<!-- components/TripDayDetail.vue — 某天的详情:时间轴 / 景点 / 贴士 / 住宿 + 手记 -->
<template>
  <div v-if="day" ref="rootRef" class="dd">
    <header class="dd-head">
      <div class="dd-head-main">
        <span class="dd-dayno">Day {{ day.day_no }}</span>
        <span class="dd-date">{{ prettyDate(day.date) }}</span>
      </div>
      <template v-if="!editHead">
        <div v-if="day.route" class="dd-route">{{ day.route }}</div>
        <div class="dd-meta">
          <span v-if="day.transport" class="dd-chip">{{ day.transport }}</span>
          <span v-if="day.meal" class="dd-chip">含餐 {{ day.meal }}</span>
          <button type="button" class="dd-b" @click="startHead">✎ 改这天</button>
        </div>
      </template>
      <div v-else class="dd-head-edit">
        <input v-model="headDraft.route" class="dd-in" placeholder="路线,如 上海 → 赫尔辛基">
        <div class="dd-head-edit-row">
          <input v-model="headDraft.transport" class="dd-in" placeholder="交通,如 HO1607 / 大巴">
          <input v-model="headDraft.meal" class="dd-in" placeholder="含餐,如 早 / 晚">
        </div>
        <div class="dd-edit-foot">
          <span class="dd-spacer"></span>
          <button type="button" class="dd-b" @click="editHead = false">取消</button>
          <button type="button" class="dd-b primary" @click="saveHead">保存</button>
        </div>
      </div>
    </header>

    <!-- 当日时间轴。AI 写的时间到了现场常要改,所以这里是可编辑的 -->
    <TripRowsEditor
      label="行程安排"
      :rows="sched"
      :fields="SCHED_FIELDS"
      @save="saveRows('sched', $event)"
    >
      <ol v-if="sched.length" class="tl">
        <li v-for="(s, i) in sched" :key="i" :class="{ hi: s[3] }">
          <span class="tl-time">{{ s[0] }}</span>
          <span class="tl-body">
            <b>{{ s[1] }}</b>
            <em v-if="s[2]">{{ s[2] }}</em>
          </span>
        </li>
      </ol>
    </TripRowsEditor>

    <!-- 当日地图:该天有带坐标的停留点才显示 -->
    <section v-if="hasStops" class="dd-sec">
      <TripMap :days="[day]" :trip-id="tripId" title="当日路线" />
    </section>

    <!-- 地点只有一份:地图上的点和这个列表是同一批数据。
         没有坐标的地点也在这儿,只是地图上不画。 -->
    <TripRowsEditor
      label="地点"
      :rows="stops"
      :fields="STOP_FIELDS"
      hint="📍 的地点会画在地图上。新加的地点还没有坐标,在地图上点开它可以补。"
      @save="saveRows('stops', $event)"
    >
      <ul v-if="stops.length" class="dd-list">
        <li v-for="(st, i) in stops" :key="i">
          <b>{{ st.t }}</b>
          <span v-if="st.dur" class="dd-dim"> · {{ st.dur }}</span>
          <span v-if="st.lat != null" class="dd-pin" title="在地图上">📍</span>
        </li>
      </ul>
    </TripRowsEditor>

    <TripListEditor
      v-for="grp in tipGroups"
      :key="grp.key"
      :items="grp.items"
      :label="grp.label"
      can-edit
      :ai-kind="grp.ai"
      :trip-id="tripId"
      :day-no="day.day_no"
      @save="saveList(grp.key, $event)"
    />

    <section class="dd-sec">
      <div class="dd-sec-head">
        <h4 class="dd-h">住宿</h4>
        <button v-if="!editStay" type="button" class="dd-b" @click="startStay">
          {{ hasStay ? '✎ 编辑' : '＋ 添加' }}
        </button>
      </div>
      <template v-if="!editStay">
        <div v-if="hasStay" class="dd-stay">
          <div class="dd-stay-txt">
            <b>{{ stay.h }}</b>
            <span v-if="stay.a" class="dd-dim">{{ stay.a }}</span>
          </div>
          <!-- 外链到系统地图:不嵌第三方地图,既不违反 CSP 也不把坐标交出去 -->
          <a
            v-if="stayMap"
            class="dd-maplink"
            :href="stayMap"
            target="_blank"
            rel="noopener noreferrer"
          >📍 地图</a>
        </div>
        <p v-else class="dd-none">还没有内容</p>
      </template>
      <div v-else class="dd-head-edit">
        <input v-model="stayDraft.h" class="dd-in" placeholder="酒店名">
        <input v-model="stayDraft.a" class="dd-in" placeholder="地址(留空也能按名字搜地图)">
        <div class="dd-edit-foot">
          <span class="dd-spacer"></span>
          <button type="button" class="dd-b" @click="editStay = false">取消</button>
          <button type="button" class="dd-b primary" @click="saveStay">保存</button>
        </div>
      </div>
    </section>

    <!-- 照片:详情里只留一行入口,拍照上传走满屏的子页面 -->
    <section v-if="stops.length" class="dd-sec">
      <button type="button" class="dd-ph-entry" @click="openPhotos">
        <span class="dd-ph-left">
          <span class="dd-ph-t">照片</span>
          <span class="dd-ph-sub">{{ photoCount ? `${photoCount} 张` : '到了现场拍了传这儿' }}</span>
        </span>
        <span v-if="coverShas.length" class="dd-ph-covers">
          <img v-for="sha in coverShas" :key="sha" :src="coverUrl(sha)" alt="">
        </span>
        <span class="dd-ph-go" aria-hidden="true">›</span>
      </button>
    </section>

    <!-- 手记:存库,多端同步(原静态页只存本机) -->
    <section class="dd-sec">
      <h4 class="dd-h">我的手记</h4>
      <el-input
        v-model="journalDraft"
        type="textarea"
        :rows="4"
        placeholder="今天的见闻、花费、想记住的细节…"
        @blur="saveJournal"
      />
      <div class="dd-journal-foot">
        <span class="dd-dim">{{ journalHint }}</span>
        <el-button size="small" :loading="saving" @click="saveJournal">保存</el-button>
      </div>
    </section>
  </div>

  <el-empty v-else description="选一天看详情" :image-size="70" />

  <TripPhotoSheet
    v-if="day"
    :open="showPhotos"
    :trip-id="tripId"
    :day="day"
    :accent="accentVars"
    @close="showPhotos = false"
  />
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'
import TripMap from '@/components/TripMap.vue'
import TripPhotoSheet from '@/components/TripPhotoSheet.vue'
import TripListEditor from '@/components/TripListEditor.vue'
import TripRowsEditor from '@/components/TripRowsEditor.vue'
import { mapUrl } from '@/utils/maplink'
import { photoList, photoUrl } from '@/utils/tripPhotos'

const props = defineProps({
  tripId: { type: Number, required: true },
  day: { type: Object, default: null },
})
const emit = defineEmits(['saved'])

const journalDraft = ref('')
// 这两个开关声明在 watch 之前:下面那个 watch 是 immediate 的,setup 阶段
// 就会跑一次,声明写在后面会撞上 TDZ(整个详情面板直接白掉)
const editHead = ref(false)
const headDraft = ref({ route: '', transport: '', meal: '' })
const editStay = ref(false)
const stayDraft = ref({ h: '', a: '' })
const saving = ref(false)
const journalHint = ref('')

watch(() => props.day, (d) => {
  journalDraft.value = d?.journal || ''
  journalHint.value = ''
  // 换了一天就把没保存的编辑状态收起来,免得改着改着串到别天去
  editHead.value = false
  editStay.value = false
}, { immediate: true })

// 每行的格子:时间 / 事项 / 备注 / 是否重点(重点那格是 0|1,不是文字)
const SCHED_FIELDS = [
  { i: 0, label: '时间', narrow: true, placeholder: '09:00' },
  { i: 3, label: '标为重点', flag: true },
  { i: 1, label: '事项', placeholder: '做什么' },
  { i: 2, label: '备注', placeholder: '备注,可留空' },
]
// 地点是对象(坐标、介绍、照片都挂在上面),所以用 k 而不是 i——
// 编辑器会把没编辑的字段原样带回去
const STOP_FIELDS = [
  { k: 'dur', label: '停留时长', narrow: true, placeholder: '15min' },
  { k: 't', label: '名称', placeholder: '地点名' },
]

const detail = computed(() => props.day?.detail || {})
const sched = computed(() => detail.value.sched || [])
const stay = computed(() => detail.value.stay || null)
// 有经纬度就精确落点,只填了酒店名也能按名字搜——所以这个链接几乎总是可用的
const stayMap = computed(() => {
  const s = stay.value
  return s ? mapUrl({ lat: s.lat, lng: s.lng, name: s.h, addr: s.a }) : ''
})
const hasStay = computed(() => !!(stay.value && (stay.value.h || stay.value.a)))
const stops = computed(() => detail.value.stops || [])
const hasStops = computed(() =>
  stops.value.some(s => isFinite(Number(s.lat)) && isFinite(Number(s.lng))))

const showPhotos = ref(false)
const rootRef = ref(null)
// 子页面 teleport 到 body,拿不到外层 .travel-page 上的主题色,打开前读出来带过去
const accentVars = ref({})
function openPhotos() {
  const el = rootRef.value
  if (el) {
    const cs = getComputedStyle(el)
    const out = {}
    for (const k of ['--trip-accent', '--trip-accent-weak', '--trip-accent-ink']) {
      const v = cs.getPropertyValue(k).trim()
      if (v) out[k] = v
    }
    accentVars.value = out
  }
  showPhotos.value = true
}
const allShas = computed(() => stops.value.flatMap(st => photoList(st)))
const photoCount = computed(() => allShas.value.length)
const coverShas = computed(() => allShas.value.slice(0, 3))
function coverUrl(sha) { return photoUrl({ tripId: props.tripId }, sha) }
const tipGroups = computed(() => [
  { key: 'todo', label: '贴士', ai: 'day_tips', items: detail.value.todo || [] },
  { key: 'cam', label: '拍摄建议', ai: 'day_cam', items: detail.value.cam || [] },
  { key: 'buy', label: '买什么', ai: 'day_buy', items: detail.value.buy || [] },
  { key: 'warn', label: '注意', ai: 'day_warn', items: detail.value.warn || [] },
])

function saveList(key, items) {
  return saveDetail(key, items.length ? items : undefined)
}

function startHead() {
  const d = props.day || {}
  headDraft.value = { route: d.route || '', transport: d.transport || '', meal: d.meal || '' }
  editHead.value = true
}

async function saveHead() {
  const next = {
    route: headDraft.value.route.trim(),
    transport: headDraft.value.transport.trim(),
    meal: headDraft.value.meal.trim(),
  }
  const before = { route: props.day.route, transport: props.day.transport, meal: props.day.meal }
  Object.assign(props.day, next)        // 先改本地,父组件 days 里是同一个对象
  editHead.value = false
  try {
    await api.patch(`/api/trips/${props.tripId}/days/${props.day.day_no}`, next)
  } catch {
    Object.assign(props.day, before)
    ElMessage.error('保存失败')
  }
}

function startStay() {
  stayDraft.value = { h: stay.value?.h || '', a: stay.value?.a || '' }
  editStay.value = true
}

function saveStay() {
  const h = stayDraft.value.h.trim()
  const a = stayDraft.value.a.trim()
  // 坐标是 AI / 导入时带来的,手改名字不该把它丢掉——留着地图才能精确落点
  const next = { ...(stay.value || {}), h, a }
  if (!h) delete next.h
  if (!a) delete next.a
  editStay.value = false
  return saveDetail('stay', (h || a) ? next : undefined)
}

/** detail 里某一块的保存。整块 detail 一起 PATCH(后端就是整体替换),
 *  所以要直接改 props.day.detail 上那个对象,父组件手里是同一个。 */
async function saveDetail(key, value) {
  const d = props.day?.detail
  if (!d) return
  const had = key in d
  const before = d[key]
  if (value === undefined) delete d[key]
  else d[key] = value
  try {
    await api.patch(`/api/trips/${props.tripId}/days/${props.day.day_no}`, { detail: d })
  } catch {
    if (had) d[key] = before
    else delete d[key]
    ElMessage.error('保存失败')
  }
}

function saveRows(key, rows) {
  return saveDetail(key, rows.length ? rows : undefined)
}

function prettyDate(iso) {
  if (!iso) return ''
  const d = new Date(iso + 'T00:00:00')
  const w = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()]
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日 · ${w}`
}

async function saveJournal() {
  if (!props.day) return
  const next = journalDraft.value
  if (next === (props.day.journal || '')) return   // 没改就不发请求
  saving.value = true
  try {
    await api.patch(`/api/trips/${props.tripId}/days/${props.day.day_no}`, { journal: next })
    journalHint.value = '已保存'
    emit('saved', { day_no: props.day.day_no, journal: next })
  } catch {
    ElMessage.error('手记保存失败')
    journalHint.value = ''
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.dd-sec-head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.dd-pin { font-size: 11px; margin-left: 4px; }
.dd-none { margin: 0; font-size: 12px; color: var(--color-text-muted); }
.dd-spacer { flex: 1; }
.dd-b {
  appearance: none; border: 1px solid var(--color-border-light); background: var(--color-surface);
  color: var(--color-text-muted); font: inherit; font-size: 11.5px;
  padding: 3px 12px; border-radius: 999px; cursor: pointer; flex: 0 0 auto;
}
.dd-b.primary {
  background: var(--trip-accent, var(--color-primary));
  border-color: var(--trip-accent, var(--color-primary)); color: #fff; font-weight: 700;
}
.dd-head-edit { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
.dd-head-edit-row { display: flex; gap: 6px; }
.dd-head-edit-row .dd-in { flex: 1; min-width: 0; }
.dd-in {
  width: 100%; box-sizing: border-box; font: inherit; font-size: 13px;
  border: 1px solid var(--color-border-light); border-radius: 8px; padding: 6px 8px;
  background: var(--color-surface); color: var(--color-text);
}
.dd-in:focus { outline: none; border-color: var(--trip-accent, var(--color-primary)); }
.dd-edit-foot { display: flex; align-items: center; gap: 8px; }

.dd-head { padding-bottom: 10px; border-bottom: 1px solid var(--trip-line, var(--color-border-light)); }
.dd-head-main { display: flex; align-items: baseline; gap: 10px; }
.dd-dayno {
  font-size: 12px; font-weight: 800; letter-spacing: .06em;
  color: #fff; background: var(--trip-accent, var(--color-primary));
  padding: 2px 8px; border-radius: 999px;
}
.dd-date { font-size: 13px; color: var(--color-text-muted); font-variant-numeric: tabular-nums; }
.dd-route { margin-top: 6px; font-size: 17px; font-weight: 800; color: var(--color-text-strong); }
.dd-meta { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }
.dd-chip {
  font-size: 11px; padding: 2px 8px; border-radius: 999px;
  background: var(--trip-accent-weak, var(--color-primary-light));
  color: var(--trip-accent-ink, var(--color-text));
}

.dd-sec { margin-top: 16px; }
.dd-h {
  margin: 0 0 8px; font-size: 12px; font-weight: 800; letter-spacing: .08em;
  color: var(--trip-ink-2, var(--color-text-muted));
}

/* 当日时间轴 */
.tl { list-style: none; margin: 0; padding: 0 0 0 4px; position: relative; }
.tl::before {
  content: ''; position: absolute; left: 52px; top: 4px; bottom: 4px;
  width: 1px; background: var(--trip-line, var(--color-border-light));
}
.tl li { display: flex; gap: 14px; padding: 5px 0; position: relative; }
.tl-time {
  width: 48px; flex-shrink: 0; text-align: right;
  font-size: 12px; font-variant-numeric: tabular-nums; color: var(--color-text-muted); padding-top: 1px;
}
.tl-body { position: relative; padding-left: 12px; font-size: 13px; line-height: 1.5; }
.tl-body::before {
  content: ''; position: absolute; left: -4px; top: 6px; width: 7px; height: 7px;
  border-radius: 50%; background: var(--trip-line, var(--color-border-light));
  box-shadow: 0 0 0 2px var(--color-surface);
}
.tl li.hi .tl-body::before { background: var(--trip-accent, var(--color-primary)); }
.tl-body b { font-weight: 700; color: var(--color-text); }
.tl-body em { display: block; font-style: normal; font-size: 12px; color: var(--color-text-muted); }

.dd-list { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.7; }
.dd-tips li { color: var(--color-text); }
.dd-dim { color: var(--color-text-muted); font-size: 12px; }
.dd-stay { font-size: 13px; display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.dd-stay-txt { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.dd-maplink {
  flex-shrink: 0; font-size: 12px; font-weight: 700; text-decoration: none;
  color: var(--trip-accent, var(--color-primary));
  border: 1px solid var(--trip-accent, var(--color-primary));
  border-radius: 999px; padding: 3px 10px; line-height: 1.5;
}
.dd-maplink:hover { background: var(--trip-accent, var(--color-primary)); color: #fff; }
.dd-journal-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; }
/* 照片入口:一行,右边压三张缩略图当预览 */
.dd-ph-entry {
  width: 100%; appearance: none; cursor: pointer; font: inherit; text-align: left;
  display: flex; align-items: center; gap: 12px;
  padding: 10px 12px; border-radius: 12px;
  border: 1px solid var(--trip-line, var(--color-border-light));
  background: var(--color-surface);
}
.dd-ph-entry:hover { border-color: var(--trip-accent, var(--color-primary)); }
.dd-ph-left { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.dd-ph-t { font-size: 13px; font-weight: 800; color: var(--color-text-strong); }
.dd-ph-sub { font-size: 11.5px; color: var(--color-text-muted); }
.dd-ph-covers { display: flex; flex-shrink: 0; }
.dd-ph-covers img {
  width: 34px; height: 34px; border-radius: 8px; object-fit: cover;
  border: 2px solid var(--color-surface); margin-left: -10px;
}
.dd-ph-covers img:first-child { margin-left: 0; }
.dd-ph-go { flex-shrink: 0; font-size: 19px; color: var(--color-text-muted); line-height: 1; }
</style>
