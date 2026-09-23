<!-- components/TripPhotoSheet.vue — 当天照片的独立子页面

     原来把每个停留点的上传位直接铺在当天详情里,手机上五个虚线大方块
     连着排下去,行程和手记全被挤到屏幕外——那样不对。照片是"到了现场
     才会用"的功能,给它一个满屏的子页面,详情里只留一行入口。 -->
<template>
  <teleport to="body">
    <transition name="phs">
      <div v-if="open" class="phs" :style="accent">
        <header class="phs-bar">
          <button class="phs-back" @click="$emit('close')">
            <span aria-hidden="true">‹</span> 返回
          </button>
          <div class="phs-title">
            <b>照片</b>
            <span>Day {{ day?.day_no }} · {{ prettyDate(day?.date) }}</span>
          </div>
          <button
            class="phs-edit"
            :class="{ on: editing }"
            :disabled="!total"
            @click="editing = !editing"
          >{{ editing ? '完成' : '管理' }}</button>
        </header>

        <div class="phs-body">
          <p v-if="!stops.length" class="phs-empty">这一天还没有标记地点,先在行程里加地点再拍照。</p>

          <section v-for="(st, si) in stops" :key="si" class="phs-sec">
            <div class="phs-sec-h">
              <span class="phs-name">{{ st.t || `地点 ${si + 1}` }}</span>
              <span class="phs-n">{{ photosOf(si).length || '还没拍' }}{{ photosOf(si).length ? ' 张' : '' }}</span>
            </div>

            <div class="phs-grid">
              <button
                v-for="(sha, i) in photosOf(si)"
                :key="sha"
                type="button"
                class="phs-cell"
                @click="open3(si, i)"
              >
                <img :src="url(sha)" alt="" loading="lazy">
                <span
                  v-if="editing"
                  class="phs-x"
                  role="button"
                  aria-label="删除这张"
                  @click.stop="drop(si, i)"
                >×</span>
              </button>

              <button
                type="button"
                class="phs-cell phs-add"
                :class="{ busy: busy === si }"
                :disabled="busy !== null"
                @click="askSource(si)"
              >
                <span v-if="busy === si" class="phs-add-t">上传中…</span>
                <template v-else>
                  <span class="phs-add-i">＋</span>
                  <span class="phs-add-t">加照片</span>
                </template>
              </button>
            </div>
          </section>

          <p v-if="err" class="phs-err">{{ err }}</p>
        </div>

        <!-- 拍照还是从相册选,交给用户决定:直接 capture 会二话不说唤起相机,
             想传之前拍好的照片就没路径了 -->
        <input ref="camRef" type="file" accept="image/*" capture="environment" hidden @change="onFiles">
        <input ref="libRef" type="file" accept="image/*" multiple hidden @change="onFiles">

        <transition name="phs-pick">
          <div v-if="picking !== null" class="phs-pick" @click.self="picking = null">
            <div class="phs-pick-box">
              <button type="button" @click="use('cam')">📷 拍照</button>
              <button type="button" @click="use('lib')">🖼 从相册选</button>
              <button type="button" class="cancel" @click="picking = null">取消</button>
            </div>
          </div>
        </transition>

        <TripPhotoViewer
          :photos="viewPhotos"
          :index="viewIndex"
          :trip-id="tripId"
          @update:index="viewIndex = $event"
          @close="viewIndex = null"
        />
      </div>
    </transition>
  </teleport>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import TripPhotoViewer from '@/components/TripPhotoViewer.vue'
import { photoList, photoUrl, uploadPhoto } from '@/utils/tripPhotos'

const props = defineProps({
  open: { type: Boolean, default: false },
  tripId: { type: Number, required: true },
  day: { type: Object, default: null },
  accent: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['close', 'changed'])

const editing = ref(false)
const busy = ref(null)
const err = ref('')
const viewIndex = ref(null)
const viewStop = ref(0)

watch(() => props.open, (v) => {
  if (!v) { editing.value = false; err.value = ''; viewIndex.value = null }
  // 子页面盖住整屏时锁掉背景滚动,否则手指滑动会带着下面的抽屉一起走
  if (typeof document !== 'undefined') {
    document.body.style.overflow = v ? 'hidden' : ''
  }
})

const stops = computed(() => props.day?.detail?.stops || [])
const total = computed(() => stops.value.reduce((n, s) => n + photoList(s).length, 0))

function photosOf(si) { return photoList(stops.value[si]) }
function url(sha) { return photoUrl({ tripId: props.tripId }, sha) }

const viewPhotos = computed(() => photosOf(viewStop.value))
function open3(si, i) { viewStop.value = si; viewIndex.value = i }

function prettyDate(iso) {
  if (!iso) return ''
  const d = new Date(iso + 'T00:00:00')
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日`
}

/** 照片挂在 detail_json 的停留点上,所以要连着整个 detail 一起 PATCH。
 *  直接改 props.day 里那个对象——它就是父组件 days 里的同一个,
 *  改完地图弹窗、分享页的封面都跟着变。 */
async function persist(si, photos) {
  const st = props.day?.detail?.stops?.[si]
  if (!st) return
  const before = { photos: st.photos, photo: st.photo }
  st.photos = photos
  delete st.photo                     // 统一到数组,别留两份真相
  try {
    const { default: api } = await import('@/api')
    await api.patch(`/api/trips/${props.tripId}/days/${props.day.day_no}`,
                    { detail: props.day.detail })
    emit('changed')
  } catch (e) {
    Object.assign(st, before)         // 失败回滚,不然界面显示的是没存上的状态
    err.value = e?.response?.data?.error || '保存失败'
  }
}

const picking = ref(null)
const camRef = ref(null)
const libRef = ref(null)

function askSource(si) { picking.value = si }
function use(kind) {
  const el = kind === 'cam' ? camRef.value : libRef.value
  el?.click()
}

async function onFiles(e) {
  const si = picking.value
  const files = [...(e.target.files || [])]
  e.target.value = ''
  picking.value = null
  if (si === null || !files.length) return
  busy.value = si
  err.value = ''
  const next = [...photosOf(si)]
  try {
    for (const f of files) {
      const sha = await uploadPhoto(props.tripId, f)
      if (!next.includes(sha)) next.push(sha)   // 内容寻址,同一张图天然去重
    }
    await persist(si, next)
  } catch (e2) {
    err.value = e2?.response?.data?.error || '上传失败'
  } finally {
    busy.value = null
  }
}

function drop(si, i) {
  persist(si, photosOf(si).filter((_, k) => k !== i))
}
</script>

<style>
/* teleport 到 body,不能 scoped */
.phs {
  position: fixed; inset: 0; z-index: 3300;
  background: var(--color-bg, #f5f3ea);
  display: flex; flex-direction: column;
}
.phs-enter-active, .phs-leave-active { transition: transform .2s ease, opacity .2s ease; }
.phs-enter-from, .phs-leave-to { transform: translateY(16px); opacity: 0; }

.phs-bar {
  flex-shrink: 0;
  display: grid; grid-template-columns: 64px 1fr 56px; align-items: center;
  gap: 8px; padding: 10px 12px;
  padding-top: calc(10px + env(safe-area-inset-top, 0px));
  background: var(--trip-accent-weak, #dce7ea);
  border-bottom: 1px solid var(--trip-accent, #2B6A80);
}
.phs-back, .phs-edit {
  appearance: none; border: 0; background: none; cursor: pointer; font: inherit;
  font-size: 13px; color: var(--trip-accent-ink, #17414f); padding: 6px 0;
}
.phs-back span { font-size: 19px; line-height: 1; vertical-align: -2px; }
.phs-edit { text-align: right; font-weight: 700; }
.phs-edit:disabled { opacity: .35; cursor: default; }
.phs-edit.on { color: var(--color-error, #e05a5a); }
.phs-title { text-align: center; line-height: 1.25; color: var(--trip-accent-ink, #17414f); }
.phs-title b { display: block; font-size: 15px; font-weight: 800; }
.phs-title span { font-size: 11px; opacity: .75; }

.phs-body {
  flex: 1; overflow-y: auto; -webkit-overflow-scrolling: touch;
  padding: 14px 12px calc(28px + env(safe-area-inset-bottom, 0px));
}
.phs-sec + .phs-sec { margin-top: 20px; }
.phs-sec-h { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin-bottom: 7px; }
.phs-name { font-size: 14px; font-weight: 800; color: var(--color-text-strong); }
.phs-n { font-size: 11px; color: var(--color-text-muted); font-variant-numeric: tabular-nums; }

.phs-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 7px; }
@media (min-width: 560px) { .phs-grid { grid-template-columns: repeat(4, 1fr); } }
@media (min-width: 860px) {
  .phs-body { max-width: 860px; margin: 0 auto; width: 100%; }
  .phs-grid { grid-template-columns: repeat(6, 1fr); }
}
.phs-cell {
  position: relative; appearance: none; padding: 0; cursor: pointer;
  aspect-ratio: 1; border-radius: 10px; overflow: hidden;
  border: 1px solid var(--color-border-light, #e3ddd0);
  background: var(--color-surface, #fff);
}
.phs-cell img { width: 100%; height: 100%; object-fit: cover; display: block; }
.phs-x {
  position: absolute; right: 4px; top: 4px;
  width: 22px; height: 22px; border-radius: 50%; line-height: 21px; text-align: center;
  background: rgba(0, 0, 0, .6); color: #fff; font-size: 15px;
}
.phs-add {
  appearance: none; font: inherit; cursor: pointer;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
  border: 1.5px dashed var(--trip-accent, #2B6A80);
  color: var(--trip-accent, #2B6A80);
  background: color-mix(in srgb, var(--trip-accent-weak, #dce7ea) 50%, transparent);
}
.phs-add.busy { opacity: .6; }
.phs-add-i { font-size: 21px; line-height: 1; }
.phs-add-t { font-size: 11px; }
.phs-empty, .phs-err { font-size: 13px; color: var(--color-text-muted); padding: 8px 2px; }

/* 来源选择 */
.phs-pick {
  position: absolute; inset: 0; z-index: 2;
  background: rgba(20, 26, 30, .45);
  display: flex; align-items: flex-end; justify-content: center;
  padding: 12px;
  padding-bottom: calc(12px + env(safe-area-inset-bottom, 0px));
}
.phs-pick-box {
  width: min(420px, 100%); display: flex; flex-direction: column; gap: 8px;
}
.phs-pick-box button {
  appearance: none; border: 0; cursor: pointer; font: inherit;
  font-size: 15px; font-weight: 700; padding: 14px;
  border-radius: 14px; background: var(--color-surface, #fff);
  color: var(--color-text-strong, #2A3D45);
}
.phs-pick-box button.cancel { color: var(--color-text-muted); font-weight: 500; }
.phs-pick-enter-active, .phs-pick-leave-active { transition: opacity .16s ease; }
.phs-pick-enter-from, .phs-pick-leave-to { opacity: 0; }
.phs-err { color: var(--color-error, #e05a5a); }
</style>
