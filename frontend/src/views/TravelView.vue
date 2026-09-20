<template>
  <!-- accent 作用域只在这一层:外壳仍是应用统一风格,内容区按行程主题换色 -->
  <div class="travel-page" :style="accentVars">
    <div class="page-header">
      <h2 class="page-title">🧳 旅行计划</h2>
      <div class="page-header-actions">
        <el-select
          v-if="trips.length"
          v-model="currentTripId"
          size="small"
          class="trip-select"
          @change="loadTrip"
        >
          <el-option
            v-for="t in trips"
            :key="t.id"
            :label="`${t.title}（${t.start_date.slice(5)}–${t.end_date.slice(5)}）`"
            :value="t.id"
          />
        </el-select>
        <el-button v-if="trip" size="small" @click="openShare">🔗 分享</el-button>
        <el-button size="small" type="primary" @click="showCreate = true">+ 新建行程</el-button>
      </div>
    </div>

    <el-empty
      v-if="!loading && !trips.length"
      description="还没有行程。新建一个，日历会按起止日期自动铺好每一天。"
    >
      <el-button type="primary" @click="showCreate = true">新建行程</el-button>
    </el-empty>

    <template v-else-if="trip">
      <!-- hero:行程标题 + 倒计时 -->
      <div class="trip-hero animal-pop" :style="{ '--i': 0 }">
        <div class="hero-main">
          <div v-if="trip.code" class="hero-code">{{ trip.code }}</div>
          <h3 class="hero-title">{{ trip.title }}</h3>
          <div v-if="trip.subtitle" class="hero-sub">{{ trip.subtitle }}</div>
          <div class="hero-range">{{ trip.start_date }} — {{ trip.end_date }} · 共 {{ days.length }} 天</div>
        </div>
        <div class="hero-count">
          <b>{{ countdown.value }}</b>
          <span>{{ countdown.label }}</span>
        </div>
      </div>

      <div class="trip-tabs">
        <button
          v-for="t in TABS"
          :key="t.key"
          type="button"
          class="trip-tab"
          :class="{ on: tab === t.key }"
          @click="tab = t.key"
        >{{ t.label }}</button>
      </div>

      <!-- 打包 -->
      <div v-if="tab === 'pack'" class="trip-panel animal-pop" :style="{ '--i': 1 }">
        <TripPacking :trip-id="trip.id" :packing="packing" @changed="loadTrip" />
      </div>

      <!-- 速查 -->
      <div v-else-if="tab === 'facts'" class="trip-panel animal-pop" :style="{ '--i': 1 }">
        <TripFacts :trip-id="trip.id" :facts="facts" @changed="loadTrip" />
      </div>

      <!-- 行程:宽屏 日历 + 右侧详情(master-detail);窄屏 点开抽屉 -->
      <div v-else class="trip-body">
        <div class="trip-cal animal-pop" :style="{ '--i': 1 }">
          <div class="pane-switch">
            <button
              v-for="m in ['calendar', 'map']"
              :key="m"
              type="button"
              class="pane-btn"
              :class="{ on: leftMode === m }"
              @click="leftMode = m"
            >{{ m === 'calendar' ? '日历' : '全程地图' }}</button>
          </div>

          <TripCalendar
            v-if="leftMode === 'calendar'"
            :trip="trip"
            :days="days"
            :selected-day-no="selectedDayNo"
            @select="onSelectDay"
          />
          <TripMap v-else :days="days" :trip-id="trip.id" title="全程路线" />
        </div>

        <div v-if="isWide" class="trip-detail animal-pop" :style="{ '--i': 2 }">
          <TripDayDetail :trip-id="trip.id" :day="selectedDay" @saved="onJournalSaved" />
        </div>
      </div>

      <!-- 移动端:底部抽屉展示当天详情 -->
      <el-drawer
        v-if="!isWide && tab === 'days'"
        v-model="showDrawer"
        direction="btt"
        size="86%"
        :with-header="false"
        class="trip-drawer"
      >
        <div class="drawer-inner-pad" :style="accentVars">
          <TripDayDetail :trip-id="trip.id" :day="selectedDay" @saved="onJournalSaved" />
        </div>
      </el-drawer>
    </template>

    <!-- 分享链接 -->
    <el-dialog v-model="showShare" title="分享这份行程" :width="dialogWidth">
      <p class="share-note">
        生成一个公开只读链接,拿到链接的人无需登录即可查看<b>行程安排、景点与地图</b>。
        <br>
        <b>不会分享</b>:你的手记、打包清单,以及记账本的任何内容。
      </p>

      <div v-if="shareUrl" class="share-box">
        <el-input :model-value="shareUrl" readonly>
          <template #append>
            <el-button @click="copyShare">复制</el-button>
          </template>
        </el-input>
        <div class="share-actions">
          <el-button size="small" type="danger" plain :loading="sharing" @click="revokeShare">
            取消分享(链接立即失效)
          </el-button>
        </div>
      </div>
      <div v-else class="share-box">
        <el-button type="primary" :loading="sharing" @click="createShare">生成分享链接</el-button>
      </div>
    </el-dialog>

    <!-- 新建行程 -->
    <el-dialog v-model="showCreate" title="新建行程" :width="dialogWidth">
      <el-form label-width="76px" size="small">
        <el-form-item label="名称">
          <el-input v-model="form.title" placeholder="如：逃离地球计划" />
        </el-form-item>
        <el-form-item label="副标题">
          <el-input v-model="form.subtitle" placeholder="如：北欧四国 · 冰岛四晚" />
        </el-form-item>
        <el-form-item label="编号">
          <el-input v-model="form.code" placeholder="团号 / 自定义，可空" />
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker
            v-model="form.range"
            type="daterange"
            value-format="YYYY-MM-DD"
            start-placeholder="出发"
            end-placeholder="返程"
            style="width:100%"
          />
        </el-form-item>
        <el-form-item label="主题色">
          <div class="accent-picker">
            <button
              v-for="a in ACCENT_LIST"
              :key="a.key"
              type="button"
              class="accent-dot"
              :class="{ on: form.accent === a.key }"
              :style="{ background: a.color }"
              :title="a.label"
              @click="form.accent = a.key"
            />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createTrip">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'
import TripCalendar from '@/components/TripCalendar.vue'
import TripMap from '@/components/TripMap.vue'
import TripPacking from '@/components/TripPacking.vue'
import TripFacts from '@/components/TripFacts.vue'
import TripDayDetail from '@/components/TripDayDetail.vue'

// 每趟旅行的主题色预设(与后端 ACCENTS 对齐)
const ACCENTS = {
  glacier: { label: '冰川', color: '#2B6A80', weak: '#D9E6EB', ink: '#17414f' },
  aurora:  { label: '极光', color: '#3C8C6E', weak: '#D8EBE2', ink: '#215240' },
  ember:   { label: '余烬', color: '#9A5A2C', weak: '#F3E6D8', ink: '#5e3418' },
  sakura:  { label: '樱', color: '#B4576F', weak: '#F6E1E6', ink: '#6d2f3f' },
  desert:  { label: '沙', color: '#A8843C', weak: '#F2E9D4', ink: '#5f4a1c' },
  violet:  { label: '夜紫', color: '#6A5A9A', weak: '#E5E1F1', ink: '#3d3363' },
}
const ACCENT_LIST = Object.entries(ACCENTS).map(([key, v]) => ({ key, ...v }))

const trips = ref([])
const trip = ref(null)
const days = ref([])
const packing = ref([])
const facts = ref([])
const currentTripId = ref(null)
const selectedDayNo = ref(0)
const loading = ref(true)
const showCreate = ref(false)
const creating = ref(false)
const showDrawer = ref(false)
const leftMode = ref('calendar')   // calendar | map
const TABS = [
  { key: 'days', label: '行程' },
  { key: 'pack', label: '打包' },
  { key: 'facts', label: '速查' },
]
const tab = ref('days')
const showShare = ref(false)
const sharing = ref(false)
const shareToken = ref('')
const shareUrl = computed(() =>
  shareToken.value ? `${window.location.origin}/s/${shareToken.value}` : '')

const form = reactive({ title: '', subtitle: '', code: '', range: [], accent: 'glacier' })

// 宽屏 master-detail / 窄屏抽屉
const isWide = ref(window.innerWidth >= 1024)
function onResize() { isWide.value = window.innerWidth >= 1024 }
onMounted(() => window.addEventListener('resize', onResize))
onBeforeUnmount(() => window.removeEventListener('resize', onResize))

const dialogWidth = computed(() => window.innerWidth < 768 ? 'calc(100vw - 28px)' : '440px')

const accentVars = computed(() => {
  const a = ACCENTS[trip.value?.accent] || ACCENTS.glacier
  return {
    '--trip-accent': a.color,
    '--trip-accent-weak': a.weak,
    '--trip-accent-ink': a.ink,
  }
})

const selectedDay = computed(() =>
  days.value.find(d => d.day_no === selectedDayNo.value) || null)

const countdown = computed(() => {
  if (!trip.value) return { value: '—', label: '' }
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const s = new Date(trip.value.start_date + 'T00:00:00')
  const e = new Date(trip.value.end_date + 'T00:00:00')
  const day = 864e5
  if (today < s) return { value: Math.round((s - today) / day), label: '天后出发' }
  if (today > e) return { value: '已结束', label: trip.value.end_date }
  return { value: `第 ${Math.round((today - s) / day) + 1} 天`, label: '旅途中' }
})

function onSelectDay(dayNo) {
  selectedDayNo.value = dayNo
  if (!isWide.value) showDrawer.value = true
}

/** 手记保存后同步到本地列表,日历上的 ✎ 标记即时生效,不用整体重拉。 */
function onJournalSaved({ day_no, journal }) {
  const d = days.value.find(x => x.day_no === day_no)
  if (d) d.journal = journal
}

async function loadTrips() {
  loading.value = true
  try {
    const res = await api.get('/api/trips')
    trips.value = res.data || []
    if (trips.value.length) {
      // 默认选「进行中」的那趟,否则最近一趟
      const ongoing = trips.value.find(t => t.status === 'ongoing')
      currentTripId.value = (ongoing || trips.value[0]).id
      await loadTrip()
    }
  } finally {
    loading.value = false
  }
}

async function loadTrip() {
  if (!currentTripId.value) return
  const res = await api.get(`/api/trips/${currentTripId.value}`)
  trip.value = res.data.trip
  days.value = res.data.days || []
  packing.value = res.data.packing || []
  facts.value = res.data.facts || []
  // 默认落在今天(若在行程内),否则第一天
  const todayIso = new Date().toISOString().slice(0, 10)
  const today = days.value.find(d => d.date === todayIso)
  selectedDayNo.value = today ? today.day_no : (days.value[0]?.day_no || 0)
}

async function createTrip() {
  if (!form.title.trim()) { ElMessage.warning('请填写行程名称'); return }
  if (!form.range || form.range.length !== 2) { ElMessage.warning('请选择起止日期'); return }
  creating.value = true
  try {
    const res = await api.post('/api/trips', {
      title: form.title, subtitle: form.subtitle, code: form.code,
      start_date: form.range[0], end_date: form.range[1], accent: form.accent,
    })
    ElMessage.success('已创建')
    showCreate.value = false
    Object.assign(form, { title: '', subtitle: '', code: '', range: [], accent: 'glacier' })
    await loadTrips()
    currentTripId.value = res.data.id
    await loadTrip()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || '创建失败')
  } finally {
    creating.value = false
  }
}

async function openShare() {
  showShare.value = true
  shareToken.value = ''
  try {
    const res = await api.get(`/api/trips/${trip.value.id}/share`)
    if (res.data.shared) shareToken.value = res.data.token
  } catch { /* 拦截器已提示 */ }
}

async function createShare() {
  sharing.value = true
  try {
    const res = await api.post(`/api/trips/${trip.value.id}/share`)
    shareToken.value = res.data.token
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || '生成失败')
  } finally {
    sharing.value = false
  }
}

async function revokeShare() {
  sharing.value = true
  try {
    await api.delete(`/api/trips/${trip.value.id}/share`)
    shareToken.value = ''
    ElMessage.success('已取消分享,旧链接立即失效')
  } catch {
    ElMessage.error('取消失败')
  } finally {
    sharing.value = false
  }
}

async function copyShare() {
  try {
    await navigator.clipboard.writeText(shareUrl.value)
    ElMessage.success('链接已复制')
  } catch {
    ElMessage.info('复制失败,请手动选中链接复制')
  }
}

onMounted(loadTrips)
</script>

<style scoped>
.page-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.page-title { font-size: 20px; font-weight: 700; color: var(--color-text); }
.page-header-actions { display: flex; align-items: center; gap: 8px; }
.trip-select { min-width: 190px; }

.trip-hero {
  margin: 14px 0 16px;
  padding: 16px 20px;
  border-radius: var(--radius-tile-large, 20px);
  background: var(--trip-accent-weak);
  border: 2px solid var(--trip-accent);
  box-shadow: 0 4px 0 0 var(--shadow-anchor);
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
}
.hero-code {
  font-size: 11px; letter-spacing: .1em; color: var(--trip-accent-ink);
  opacity: .75; font-variant-numeric: tabular-nums;
}
.hero-title { margin: 2px 0 0; font-size: 20px; font-weight: 800; color: var(--trip-accent-ink); }
.hero-sub { font-size: 13px; color: var(--trip-accent-ink); opacity: .8; margin-top: 2px; }
.hero-range { font-size: 12px; color: var(--trip-accent-ink); opacity: .7; margin-top: 6px; font-variant-numeric: tabular-nums; }
.hero-count { text-align: center; flex-shrink: 0; }
.hero-count b { display: block; font-size: 22px; font-weight: 900; color: var(--trip-accent); font-variant-numeric: tabular-nums; }
.hero-count span { font-size: 11px; color: var(--trip-accent-ink); opacity: .75; }

/* 宽屏:左日历 + 右详情 */
.trip-body { display: grid; grid-template-columns: 1fr; gap: 16px; }
@media (min-width: 1024px) {
  .trip-body { grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); align-items: start; }
  .trip-detail { position: sticky; top: 12px; max-height: calc(100dvh - 90px); overflow-y: auto; }
}
.trip-cal, .trip-detail {
  background: var(--color-surface);
  border: 2px solid var(--color-border-light);
  border-radius: var(--radius-tile-large, 20px);
  box-shadow: 0 4px 0 0 var(--shadow-anchor-light);
  padding: 14px;
}

.trip-tabs { display: flex; gap: 6px; margin-bottom: 14px; flex-wrap: wrap; }
.trip-tab {
  appearance: none; border: 2px solid var(--color-border-light);
  background: var(--color-surface); color: var(--color-text-muted);
  font: inherit; font-size: 13px; font-weight: 700;
  padding: 5px 16px; border-radius: 999px; cursor: pointer;
  box-shadow: 0 2px 0 0 var(--shadow-anchor-light);
}
.trip-tab.on {
  background: var(--trip-accent); border-color: var(--trip-accent); color: #fff;
}
.trip-panel {
  background: var(--color-surface);
  border: 2px solid var(--color-border-light);
  border-radius: var(--radius-tile-large, 20px);
  box-shadow: 0 4px 0 0 var(--shadow-anchor-light);
  padding: 16px;
}

.share-note { font-size: 13px; line-height: 1.7; color: var(--color-text); margin: 0 0 12px; }
.share-box { display: flex; flex-direction: column; gap: 10px; }
.share-actions { display: flex; justify-content: flex-end; }

.pane-switch { display: flex; gap: 6px; margin-bottom: 12px; }
.pane-btn {
  appearance: none; border: 1px solid var(--color-border-light);
  background: var(--color-surface); color: var(--color-text-muted);
  font: inherit; font-size: 12px; font-weight: 700;
  padding: 4px 12px; border-radius: 999px; cursor: pointer;
}
.pane-btn.on {
  background: var(--trip-accent); border-color: var(--trip-accent); color: #fff;
}

.accent-picker { display: flex; gap: 8px; }
.accent-dot {
  width: 24px; height: 24px; border-radius: 50%;
  border: 2px solid transparent; cursor: pointer; padding: 0;
  box-shadow: 0 2px 0 0 rgba(0,0,0,.15);
}
.accent-dot.on { border-color: var(--color-text-strong); transform: scale(1.12); }

.drawer-inner-pad { padding: 16px 16px 24px; }

@media (max-width: 768px) {
  .page-header-actions { width: 100%; }
  .trip-select { flex: 1; min-width: 0; }
  .trip-hero { flex-direction: column; align-items: flex-start; gap: 10px; padding: 14px 16px; }
  .hero-count { align-self: flex-end; text-align: right; }
}
</style>
