<!-- components/TripDayDetail.vue — 某天的详情:时间轴 / 景点 / 贴士 / 住宿 + 手记 -->
<template>
  <div v-if="day" class="dd">
    <header class="dd-head">
      <div class="dd-head-main">
        <span class="dd-dayno">Day {{ day.day_no }}</span>
        <span class="dd-date">{{ prettyDate(day.date) }}</span>
      </div>
      <div v-if="day.route" class="dd-route">{{ day.route }}</div>
      <div class="dd-meta">
        <span v-if="day.transport" class="dd-chip">{{ day.transport }}</span>
        <span v-if="day.meal" class="dd-chip">含餐 {{ day.meal }}</span>
      </div>
    </header>

    <!-- 当日地图:该天有带坐标的停留点才显示 -->
    <section v-if="hasStops" class="dd-sec">
      <TripMap :days="[day]" :trip-id="tripId" title="当日路线" />
    </section>

    <!-- 当日时间轴 -->
    <section v-if="sched.length" class="dd-sec">
      <h4 class="dd-h">行程安排</h4>
      <ol class="tl">
        <li v-for="(s, i) in sched" :key="i" :class="{ hi: s[3] }">
          <span class="tl-time">{{ s[0] }}</span>
          <span class="tl-body">
            <b>{{ s[1] }}</b>
            <em v-if="s[2]">{{ s[2] }}</em>
          </span>
        </li>
      </ol>
    </section>

    <section v-if="spots.length" class="dd-sec">
      <h4 class="dd-h">景点</h4>
      <ul class="dd-list">
        <li v-for="(s, i) in spots" :key="i">
          <b>{{ s[0] }}</b><span v-if="s[1]" class="dd-dim"> · {{ s[1] }}</span>
        </li>
      </ul>
    </section>

    <section v-for="grp in tipGroups" :key="grp.key" class="dd-sec">
      <template v-if="grp.items.length">
        <h4 class="dd-h">{{ grp.label }}</h4>
        <ul class="dd-list dd-tips"><li v-for="(t, i) in grp.items" :key="i">{{ t }}</li></ul>
      </template>
    </section>

    <section v-if="stay && (stay.h || stay.a)" class="dd-sec">
      <h4 class="dd-h">住宿</h4>
      <div class="dd-stay">
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
    </section>

    <!-- 照片:到了现场直接拍了传,每个点一个位置 -->
    <section v-if="stops.length" class="dd-sec">
      <h4 class="dd-h">照片</h4>
      <div v-for="(st, si) in stops" :key="si" class="dd-ph">
        <div class="dd-ph-name">{{ st.t || `地点 ${si + 1}` }}</div>
        <TripPhotoStrip
          :photos="photosOf(st)"
          can-edit
          :trip-id="tripId"
          @change="savePhotos(si, $event)"
        />
      </div>
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
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'
import TripMap from '@/components/TripMap.vue'
import TripPhotoStrip from '@/components/TripPhotoStrip.vue'
import { mapUrl } from '@/utils/maplink'
import { photoList } from '@/utils/tripPhotos'

const props = defineProps({
  tripId: { type: Number, required: true },
  day: { type: Object, default: null },
})
const emit = defineEmits(['saved'])

const journalDraft = ref('')
const saving = ref(false)
const journalHint = ref('')

watch(() => props.day, (d) => {
  journalDraft.value = d?.journal || ''
  journalHint.value = ''
}, { immediate: true })

const detail = computed(() => props.day?.detail || {})
const sched = computed(() => detail.value.sched || [])
const spots = computed(() => detail.value.spots || [])
const stay = computed(() => detail.value.stay || null)
// 有经纬度就精确落点,只填了酒店名也能按名字搜——所以这个链接几乎总是可用的
const stayMap = computed(() => {
  const s = stay.value
  return s ? mapUrl({ lat: s.lat, lng: s.lng, name: s.h, addr: s.a }) : ''
})
const stops = computed(() => detail.value.stops || [])
const hasStops = computed(() =>
  stops.value.some(s => isFinite(Number(s.lat)) && isFinite(Number(s.lng))))

function photosOf(st) { return photoList(st) }

/** 照片挂在 detail_json 的停留点上,所以要连着整个 detail 一起 PATCH。
 *  直接改 props.day 里那个对象——它就是父组件 days 里的同一个,
 *  改完地图那边的封面图也同步。 */
async function savePhotos(si, photos) {
  const st = props.day?.detail?.stops?.[si]
  if (!st) return
  const before = { photos: st.photos, photo: st.photo }
  st.photos = photos
  delete st.photo                    // 统一到数组,别留两份真相
  try {
    await api.patch(`/api/trips/${props.tripId}/days/${props.day.day_no}`,
                    { detail: props.day.detail })
  } catch {
    Object.assign(st, before)        // 失败回滚,不然界面显示的是没存上的状态
    ElMessage.error('照片保存失败')
  }
}
const tipGroups = computed(() => [
  { key: 'todo', label: '贴士', items: detail.value.todo || [] },
  { key: 'cam', label: '拍摄建议', items: detail.value.cam || [] },
  { key: 'buy', label: '买什么', items: detail.value.buy || [] },
  { key: 'warn', label: '注意', items: detail.value.warn || [] },
])

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
.dd-ph + .dd-ph { margin-top: 12px; }
.dd-ph-name { font-size: 12.5px; font-weight: 700; color: var(--color-text); margin-bottom: 5px; }
</style>
