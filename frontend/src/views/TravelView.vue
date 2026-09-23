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
        >
          <el-option
            v-for="t in trips"
            :key="t.id"
            :label="`${t.title}（${t.start_date.slice(5)}–${t.end_date.slice(5)}）`"
            :value="t.id"
          />
        </el-select>
        <div class="header-btns">
          <el-button size="small" @click="openAi(0)">✨ AI 生成</el-button>
          <el-button size="small" type="primary" @click="showCreate = true">+ 新建</el-button>
          <!-- 不用 el-dropdown:它的触发器是个 el-button,动森主题给按钮的粗描边
               加投影,内容只有三个点时会鼓成一坨方块,看着像多了一圈框。 -->
          <div v-if="trip" class="more-wrap">
            <button
              type="button"
              class="more-btn"
              :class="{ on: showMore }"
              aria-label="更多操作"
              @click="showMore = !showMore"
            >⋯</button>
            <div v-if="showMore" class="more-mask" @click="showMore = false"></div>
            <div v-if="showMore" class="more-menu">
              <button type="button" @click="showMore = false; startEditTrip()">✎ 编辑行程信息</button>
              <button type="button" @click="showMore = false; openShare()">🔗 分享 / 导出</button>
              <button type="button" class="danger" @click="showMore = false; removeTrip()">
                🗑 删除这趟行程
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 后台还在跑的任务。放在最上面:关掉弹窗后得一眼能看见,
         否则用户根本不知道任务还在跑、也不知道去哪儿看。

         必须说清楚是**哪一趟**的:任务和当前看的行程不是一回事,
         不写出来就成了"我在看行程 A,它却显示行程 B 的进度"。 -->
    <button
      v-if="activeJob && !showAi"
      type="button"
      class="ai-strip"
      @click="resumeAi"
    >
      <span class="ai-strip-dot"></span>
      <span class="ai-strip-t">
        AI 正在生成<template v-if="activeJobTripName">:{{ activeJobTripName }}</template>…
      </span>
      <span class="ai-strip-n">{{ activeJob.done }} / {{ activeJob.total || '…' }}</span>
      <span class="ai-strip-go">查看 ›</span>
    </button>

    <el-skeleton v-if="loading" :rows="6" animated class="trip-boot" />

    <el-empty
      v-else-if="!trips.length"
      description="还没有行程。可以粘贴旅行社的行程单让 AI 整理，或者自己新建。"
    >
      <el-button type="primary" @click="openAi(0)">✨ AI 生成行程</el-button>
      <el-button @click="showCreate = true">手动新建</el-button>
    </el-empty>

    <!-- 换行程期间把内容区盖住。纯视觉的加载态不够:底下还是上一趟的日历和
         详情,点下去就改到别的行程上了。inert 连键盘和点击一起挡掉。 -->
    <template v-else-if="trip">
      <!-- 提示放在被压暗的那层**外面**,否则它自己也被压到看不清 -->
      <div v-if="loadingTrip" class="trip-swap-tip">
        <span class="trip-swap-dot"></span>正在打开…
      </div>

      <div :class="{ 'trip-swapping': loadingTrip }" :inert="loadingTrip || undefined">
      <!-- hero:行程标题 + 倒计时 -->
      <div class="trip-hero animal-pop" :style="{ '--i': 0 }">
        <div class="hero-main">
          <div v-if="trip.code" class="hero-code">{{ trip.code }}</div>
          <h3 class="hero-title">{{ trip.title }}</h3>
          <div v-if="trip.subtitle" class="hero-sub">{{ trip.subtitle }}</div>
          <p v-if="trip.cover_note" class="hero-note">{{ trip.cover_note }}</p>
          <div class="hero-range">{{ trip.start_date }} — {{ trip.end_date }} · 共 {{ days.length }} 天</div>
        </div>
        <div class="hero-count">
          <b>{{ countdown.value }}</b>
          <span>{{ countdown.label }}</span>
        </div>
      </div>

      <div v-if="blankDays && !activeJob" class="blank-tip">
        <span>还有 <b>{{ blankDays }}</b> 天没有内容</span>
        <button type="button" @click="openAi(trip.id, 'fill')">✨ 让 AI 补全</button>
      </div>

      <!-- 要说清楚是**哪几个**:只报个数字,用户根本不知道该去哪天找 -->
      <div v-if="bareList.length && !activeJob" class="blank-tip">
        <span>
          有 <b>{{ bareList.length }}</b> 个地点还没写介绍:
          <button
            v-for="b in bareList.slice(0, 6)"
            :key="b.key"
            type="button"
            class="blank-link"
            @click="gotoSpot(b)"
          >{{ b.t }}<i>D{{ b.dayNo }}</i></button>
          <template v-if="bareList.length > 6">等</template>
        </span>
        <button type="button" @click="openAi(trip.id, 'spots')">✨ 让 AI 写</button>
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

      <!-- 花费:和账本打通的那一头 -->
      <div v-else-if="tab === 'cost'" class="trip-panel animal-pop" :style="{ '--i': 1 }">
        <TripSpending :trip="trip" />
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
      </div>
    </template>

    <TripAiDialog
      :open="showAi"
      :accents="ACCENT_LIST"
      :trip-id="aiTripId"
      :job-id="aiJobId"
      :blank-days="blankDays"
      :bare-spots="bareSpots"
      :mode="aiMode"
      @close="onAiClose"
      @created="onAiDone"
    />

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

      <!-- 离线文件:在飞机上、没开漫游的时候,链接是打不开的 -->
      <div class="share-off">
        <h4>存成离线文件</h4>
        <p>
          整份行程装进<b>一个 HTML 文件</b>——样式、照片、路线示意图都在里面,
          没网也能看。用浏览器打开后按打印,就能存成 PDF。
        </p>
        <label class="share-ck">
          <input type="checkbox" v-model="exportPhotos">
          <span>包含照片（文件会大不少）</span>
        </label>
        <div class="share-dl">
          <a class="share-dl-b primary" :href="exportUrl('full')">完整版</a>
          <a class="share-dl-b" :href="exportUrl('share')">分享版</a>
        </div>
        <p class="share-dim">
          完整版含手记和打包清单,自己留着看;分享版和上面那个链接口径一致,
          可以直接发给同行的人。
        </p>
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

    <!-- 编辑行程信息。日期不在这儿改:改起止日要连带增删每一天,
         那是"重排行程"而不是"改个名字",容易把已经写好的内容冲掉。 -->
    <el-dialog v-model="showEdit" title="编辑行程信息" :width="dialogWidth">
      <el-form label-width="76px" size="small">
        <el-form-item label="名称">
          <el-input v-model="editForm.title" placeholder="如：逃离地球计划" />
        </el-form-item>
        <el-form-item label="副标题">
          <el-input v-model="editForm.subtitle" placeholder="如：北欧四国 · 冰岛四晚" />
        </el-form-item>
        <el-form-item label="编号">
          <el-input v-model="editForm.code" placeholder="团号 / 自定义，可空" />
        </el-form-item>
        <el-form-item label="卷首语">
          <el-input
            v-model="editForm.cover_note"
            type="textarea"
            :rows="2"
            placeholder="封面上那句话，可空"
          />
        </el-form-item>
        <el-form-item label="主题色">
          <div class="accent-picker">
            <button
              v-for="a in ACCENT_LIST"
              :key="a.key"
              type="button"
              class="accent-dot"
              :class="{ on: editForm.accent === a.key }"
              :style="{ background: a.color }"
              :title="a.label"
              @click="editForm.accent = a.key"
            />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="edit-hint">日期要改的话，新建一趟更稳妥</span>
        <el-button @click="showEdit = false">取消</el-button>
        <el-button type="primary" :loading="savingTrip" @click="saveTrip">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'
import TripCalendar from '@/components/TripCalendar.vue'
import TripMap from '@/components/TripMap.vue'
import TripPacking from '@/components/TripPacking.vue'
import TripFacts from '@/components/TripFacts.vue'
import TripSpending from '@/components/TripSpending.vue'
import TripDayDetail from '@/components/TripDayDetail.vue'
import TripAiDialog from '@/components/TripAiDialog.vue'
import { resumeAiBlocks } from '@/utils/aiJobs'

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
const loading = ref(true)        // 首次进页面:列表还没拉到
const loadingTrip = ref(false)   // 正在换行程:内容区还不能信
const showCreate = ref(false)
const creating = ref(false)
const showEdit = ref(false)
const savingTrip = ref(false)
const editForm = ref({ title: '', subtitle: '', code: '', cover_note: '', accent: 'glacier' })
const showDrawer = ref(false)
const leftMode = ref('calendar')   // calendar | map
const TRIP_JOB_KINDS = 'import_notice,from_idea,fill_days,fill_spots,block'
const TABS = [
  { key: 'days', label: '行程' },
  { key: 'pack', label: '打包' },
  { key: 'facts', label: '速查' },
  { key: 'cost', label: '花费' },
]
const tab = ref('days')
const showAi = ref(false)
const aiTripId = ref(0)
const aiJobId = ref(0)
const aiMode = ref('new')
const activeJob = ref(null)
let jobTimer = null

function openAi(tripId, mode = 'new') {
  aiTripId.value = tripId || 0
  aiJobId.value = 0
  aiMode.value = mode
  showAi.value = true
}
function resumeAi() {
  aiTripId.value = 0
  aiJobId.value = activeJob.value.id
  showAi.value = true
}
function onAiClose() {
  showAi.value = false
  watchJobs()            // 关掉弹窗后接着在页面上盯着
}
async function onAiDone(tripId) {
  await loadTrips()
  if (currentTripId.value === tripId) await loadTrip()   // 已经选中就手动刷一下
  else currentTripId.value = tripId                      // 否则交给 watcher
  ElMessage.success('行程已生成，内容都可以直接改')
}

/** 新建一趟的任务。它们跑完**才**有 trip_id,所以完事了跳过去是对的
 *  ——用户就是为了这趟新行程点的生成。别的类型属于某一趟已有的行程,
 *  跑完只该刷新那一趟,不该把人从正在看的地方拽走。 */
const CREATING_KINDS = ['import_notice', 'from_idea']

/** 生成跑在后端,关页面也不会停。回到这一页时接上最近那个没跑完的。 */
async function watchJobs() {
  clearTimeout(jobTimer)
  try {
    // 只看旅行相关的那几种——财务体检那类作业也在同一张表里,
    // 不筛的话旅行页会把别人的任务当成自己"生成中"的那个
    const res = await api.get('/api/ai-jobs?kinds=' + TRIP_JOB_KINDS)
    const job = (res.data || [])[0]
    const running = job && ['pending', 'running'].includes(job.status)
    const was = activeJob.value
    activeJob.value = running ? job : null
    if (running) {
      jobTimer = setTimeout(watchJobs, 3000)
      return
    }
    if (!was || job?.status !== 'done') return

    await loadTrips()
    if (CREATING_KINDS.includes(job.kind) && job.trip_id) {
      // 新建出来的那趟:跳过去(已经选中就手动刷一下,watcher 不会重复触发)
      if (currentTripId.value === job.trip_id) await loadTrip()
      else currentTripId.value = job.trip_id
      ElMessage.success('AI 生成完了，内容都可以直接改')
    } else if (job.trip_id && job.trip_id === currentTripId.value) {
      await loadTrip()
      ElMessage.success('AI 写完了，内容都可以直接改')
    } else if (job.trip_id) {
      // 别的行程的任务跑完了:说一声就行,不要把人拽走
      const t = trips.value.find(x => x.id === job.trip_id)
      ElMessage.success(`「${t?.title || '另一趟行程'}」的 AI 内容写完了`)
    }
  } catch { /* 静默:这只是个锦上添花的提示 */ }
}

const activeJobTripName = computed(() => {
  const j = activeJob.value
  if (!j?.trip_id) return ''                       // 还在建,没有行程可指
  if (j.trip_id === currentTripId.value) return ''  // 就是眼前这趟,不用重复
  return trips.value.find(t => t.id === j.trip_id)?.title || '另一趟行程'
})

const exportPhotos = ref(true)
function exportUrl(scope) {
  return `/api/trips/${trip.value?.id}/export.html`
    + `?scope=${scope}&photos=${exportPhotos.value ? 1 : 0}`
}

const showMore = ref(false)
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

/** 还空着的天数:有这几天才值得提示「让 AI 补全」。 */
const blankDays = computed(() =>
  days.value.filter(d => !Object.keys(d.detail || {}).length).length)

/** 还没有介绍的地点数。老行程(AI 功能上线前导入的)这块基本都是空的。 */
/** 还没写介绍的地点。列出来而不是只报个数——只说"有 3 个"的话,
 *  用户得一天天翻过去找是哪三个。 */
const bareList = computed(() => {
  const out = []
  const seen = new Set()
  for (const d of days.value) {
    for (const st of (d.detail?.stops || [])) {
      const name = (st?.t || '').trim()
      const key = `${d.day_no}:${name}`
      if (name && !(st.desc || '').trim() && !seen.has(key)) {
        seen.add(key)
        out.push({ key, t: name, dayNo: d.day_no })
      }
    }
  }
  return out
})
const bareSpots = computed(() => bareList.value.length)

/** 点名字就跳到那一天,顺手把视图切回「行程」。 */
function gotoSpot(b) {
  tab.value = 'days'
  onSelectDay(b.dayNo)
}

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

/** 拉行程列表。**不动用户当前的选择**——除非他选的那趟已经不在了。
 *
 *  以前这里无条件把 currentTripId 重设成"进行中的那趟",于是任何一次
 *  后台刷新(任务跑完、新建完)都会把人从正在看的行程上拽走。 */
async function loadTrips() {
  const res = await api.get('/api/trips')
  trips.value = res.data || []
  if (!trips.value.some(t => t.id === currentTripId.value)) {
    // 默认选「进行中」的那趟,否则最近一趟
    const ongoing = trips.value.find(t => t.status === 'ongoing')
    currentTripId.value = (ongoing || trips.value[0])?.id ?? null
  }
}

/** 换行程的唯一入口:改 currentTripId,下面那个 watcher 负责加载。
 *
 *  loadSeq 是请求序号:连点几下选择器时,响应回来的顺序不一定是发出去的
 *  顺序,不对号就会出现"选了 A、显示的是 B"。晚发的赢,早到的作废。 */
let loadSeq = 0

async function loadTrip(id = currentTripId.value) {
  const seq = ++loadSeq
  if (!id) {
    trip.value = null
    days.value = []
    packing.value = []
    facts.value = []
    loadingTrip.value = false
    return
  }
  loadingTrip.value = true
  try {
    const res = await api.get(`/api/trips/${id}`)
    if (seq !== loadSeq) return          // 有更新的请求在路上,这份结果作废
    // 一起换:别让子组件看到"新行程的标题 + 上一趟的日历"
    trip.value = res.data.trip
    days.value = res.data.days || []
    packing.value = res.data.packing || []
    facts.value = res.data.facts || []
    // 默认落在今天(若在行程内),否则第一天
    const todayIso = new Date().toISOString().slice(0, 10)
    const today = days.value.find(d => d.date === todayIso)
    selectedDayNo.value = today ? today.day_no : (days.value[0]?.day_no || 0)
  } catch (e) {
    if (seq === loadSeq) {
      trip.value = null
      days.value = []
    }
    throw e
  } finally {
    if (seq === loadSeq) loadingTrip.value = false
  }
}

// 选择器、新建、AI 生成完……所有换行程的路径都只改这个 id,加载只有这一处。
// 以前每条路径各自 loadTrips + loadTrip,顺序稍有不同就会互相盖。
watch(currentTripId, (id) => {
  showDrawer.value = false
  loadTrip(id).catch(() => { /* 拦截器已提示 */ })
})

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
    currentTripId.value = res.data.id      // watcher 去加载
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || '创建失败')
  } finally {
    creating.value = false
  }
}

function startEditTrip() {
  const t = trip.value
  if (!t) return
  editForm.value = {
    title: t.title || '', subtitle: t.subtitle || '', code: t.code || '',
    cover_note: t.cover_note || '', accent: t.accent || 'glacier',
  }
  showEdit.value = true
}

async function saveTrip() {
  const next = {
    title: editForm.value.title.trim(),
    subtitle: editForm.value.subtitle.trim(),
    code: editForm.value.code.trim(),
    cover_note: editForm.value.cover_note.trim(),
    accent: editForm.value.accent,
  }
  if (!next.title) {
    ElMessage.warning('名称不能为空')
    return
  }
  savingTrip.value = true
  try {
    await api.patch(`/api/trips/${trip.value.id}`, next)
    Object.assign(trip.value, next)
    // 顶上的选择器读的是 trips 列表那份,也要跟着改,否则标题两处不一致
    const row = trips.value.find(t => t.id === trip.value.id)
    if (row) Object.assign(row, { title: next.title, accent: next.accent })
    showEdit.value = false
    ElMessage.success('已保存')
  } catch {
    /* 拦截器已提示 */
  } finally {
    savingTrip.value = false
  }
}

async function removeTrip() {
  if (!trip.value) return
  try {
    await ElMessageBox.confirm(
      `删除「${trip.value.title}」?行程、手记、照片和打包进度都会一起消失。`,
      '删除行程',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '再想想',
        confirmButtonClass: 'el-button--danger' },
    )
  } catch {
    return                       // 点了取消
  }
  try {
    await api.delete(`/api/trips/${trip.value.id}`)
    ElMessage.success('已删除')
    trip.value = null
    currentTripId.value = null      // 置空 → loadTrips 会挑一趟新的出来
    await loadTrips()
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || '删除失败')
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

onMounted(async () => {
  try {
    await loadTrips()
    // currentTripId 从 null 变成某个 id 会触发 watcher;
    // 等它一下,免得"列表出来了、内容还是空的"闪一下
    if (currentTripId.value) await loadTrip()
  } finally {
    loading.value = false
  }
  watchJobs()
  resumeAiBlocks()        // 刷新前还在跑的单块生成,接着盯
})
onBeforeUnmount(() => clearTimeout(jobTimer))
</script>

<style scoped>
.trip-boot { margin-top: 16px; }
/* 换行程时压暗 + 挡住交互。位置留住不塌,否则页面会跳一下 */
.trip-swapping { opacity: .35; pointer-events: none; transition: opacity .12s ease; }
.trip-swap-tip {
  position: sticky; top: 0; z-index: 3;
  display: flex; align-items: center; gap: 8px;
  padding: 6px 12px; margin-bottom: -4px;
  font-size: 12px; color: var(--color-text-muted);
}
.trip-swap-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--trip-accent, var(--color-primary));
  animation: trip-swap-pulse 1s ease-in-out infinite;
}
@keyframes trip-swap-pulse { 50% { opacity: .25; } }

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
.hero-note {
  margin: 8px 0 0; padding-left: 9px; max-width: 46ch;
  border-left: 3px solid var(--trip-accent); font-size: 12.5px; line-height: 1.65;
  color: var(--trip-accent-ink); opacity: .85;
}
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

.header-btns { display: flex; gap: 8px; align-items: center; }
.more-wrap { position: relative; flex-shrink: 0; }
.more-btn {
  appearance: none; cursor: pointer; font: inherit; line-height: 1;
  width: 34px; height: 30px; padding: 0; border-radius: 10px;
  border: 1px solid var(--color-border-light); background: var(--color-surface);
  color: var(--color-text-muted); font-size: 17px;
}
.more-btn.on, .more-btn:hover {
  border-color: var(--color-primary); color: var(--color-primary);
}
.more-mask { position: fixed; inset: 0; z-index: 30; }
.more-menu {
  position: absolute; right: 0; top: calc(100% + 6px); z-index: 31;
  min-width: 168px; padding: 4px; border-radius: 12px;
  background: var(--color-surface);
  border: 1px solid var(--color-border-light);
  box-shadow: 0 8px 24px rgba(0, 0, 0, .14);
}
.more-menu button {
  display: block; width: 100%; text-align: left; appearance: none; border: 0;
  background: none; cursor: pointer; font: inherit; font-size: 13px;
  padding: 9px 12px; border-radius: 8px; color: var(--color-text);
  white-space: nowrap;
}
.more-menu button:hover { background: var(--color-primary-light); }
.more-menu button.danger { color: var(--color-error, #e05a5a); }
.more-menu button.danger:hover { background: rgba(224, 90, 90, .1); }

.blank-tip {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  margin-bottom: 14px; padding: 9px 14px; border-radius: 12px;
  border: 1px dashed var(--trip-accent); background: var(--trip-accent-weak);
  color: var(--trip-accent-ink); font-size: 12.5px;
}
.edit-hint { float: left; font-size: 11.5px; color: var(--color-text-muted); line-height: 32px; }
.blank-tip b { font-variant-numeric: tabular-nums; }
/* 地点名是行内链接,不是按钮——下面那条实心药丸的规则要把它排除掉,
   否则一串名字会变成一串黑疙瘩 */
.blank-tip .blank-link {
  appearance: none; border: 0; background: none; padding: 0; margin: 0; cursor: pointer;
  font: inherit; font-size: inherit; font-weight: 400;
  color: var(--trip-accent-ink); border-radius: 0;
  text-decoration: underline; text-underline-offset: 2px;
  text-decoration-color: var(--trip-accent);
}
/* 两个带下划线的名字挨在一起容易读成一个,加个分隔点 */
.blank-tip .blank-link + .blank-link::before {
  content: '、'; text-decoration: none; margin: 0 1px; opacity: .7;
}
.blank-link i { font-style: normal; font-size: 10.5px; opacity: .6; margin-left: 2px; }
.blank-tip > span { flex: 1 1 auto; min-width: 0; line-height: 1.9; }
.blank-tip > button {
  margin-left: auto; flex: 0 0 auto; appearance: none; cursor: pointer; font: inherit;
  font-size: 12.5px; font-weight: 700; padding: 4px 14px; border-radius: 999px;
  border: 1px solid var(--trip-accent); background: var(--trip-accent); color: #fff;
}

.ai-strip {
  width: 100%; appearance: none; cursor: pointer; font: inherit; text-align: left;
  display: flex; align-items: center; gap: 10px;
  /* 上面那排按钮带动森主题的投影,会探出自身盒子几像素,顶上得留够 */
  margin: 10px 0 14px; padding: 9px 14px; border-radius: 999px;
  border: 1px solid var(--color-primary); background: var(--color-primary-light);
  color: var(--color-text-strong);
}
.ai-strip-dot {
  width: 8px; height: 8px; border-radius: 50%; background: var(--color-primary);
  animation: ai-pulse 1.1s ease-in-out infinite;
}
@keyframes ai-pulse { 50% { opacity: .25; } }
.ai-strip-t { font-size: 13px; font-weight: 700; }
.ai-strip-n { font-size: 12px; color: var(--color-text-muted); font-variant-numeric: tabular-nums; }
.ai-strip-go { margin-left: auto; font-size: 12px; color: var(--color-primary); font-weight: 700; }

.share-off {
  margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--color-border-light);
}
.share-off h4 { margin: 0 0 4px; font-size: 13px; font-weight: 800; color: var(--color-text-strong); }
.share-off p { margin: 0 0 8px; font-size: 12.5px; line-height: 1.7; color: var(--color-text-muted); }
.share-ck { display: flex; align-items: center; gap: 6px; font-size: 12.5px; cursor: pointer; }
.share-ck input { accent-color: var(--color-primary); }
.share-dl { display: flex; gap: 8px; margin-top: 10px; }
.share-dl-b {
  text-decoration: none; font-size: 13px; font-weight: 700;
  padding: 6px 18px; border-radius: 999px;
  border: 1px solid var(--color-primary); color: var(--color-primary);
}
.share-dl-b.primary { background: var(--color-primary); color: #fff; }
.share-dim { margin-top: 8px !important; font-size: 11.5px !important; }

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
  /* 窄屏按钮多了会把行程选择框挤成一条缝,改成两行:选择框独占一行 */
  .page-header { align-items: stretch; }
  .page-header-actions { width: 100%; flex-wrap: wrap; gap: 8px; }
  .trip-select { flex: 1 0 100%; min-width: 0; }
  .header-btns { width: 100%; }
  .header-btns > :deep(.el-button) { flex: 1; }
  .trip-hero { flex-direction: column; align-items: flex-start; gap: 10px; padding: 14px 16px; }
  .hero-count { align-self: flex-end; text-align: right; }
}
</style>
