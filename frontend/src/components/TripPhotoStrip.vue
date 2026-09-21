<!-- components/TripPhotoStrip.vue — 一组照片的缩略图条 + 拍照上传位
     只负责展示和挑文件,存哪由父组件决定(停留点的 photos 字段在
     detail_json 里,要连着整个 detail 一起 PATCH)。 -->
<template>
  <div class="ps">
    <div v-if="label" class="ps-label">{{ label }}</div>

    <div class="ps-row">
      <button
        v-for="(sha, i) in photos"
        :key="sha"
        type="button"
        class="ps-thumb"
        :aria-label="`查看第 ${i + 1} 张照片`"
        @click="viewing = i"
      >
        <img :src="url(sha)" alt="" loading="lazy">
        <span
          v-if="canEdit"
          class="ps-x"
          role="button"
          :aria-label="`删除第 ${i + 1} 张照片`"
          @click.stop="remove(i)"
        >×</span>
      </button>

      <!-- 拍照上传位:手机上 capture 会直接唤起相机 -->
      <button v-if="canEdit" type="button" class="ps-add" :class="{ busy }" :disabled="busy" @click="picking = true">
        <span v-if="busy" class="ps-add-t">上传中…</span>
        <template v-else>
          <span class="ps-add-i">＋</span>
          <span class="ps-add-t">加照片</span>
        </template>
      </button>
      <input ref="camRef" type="file" accept="image/*" capture="environment" hidden @change="onPick">
      <input ref="libRef" type="file" accept="image/*" multiple hidden @change="onPick">

      <span v-if="!canEdit && !photos.length" class="ps-none">还没有照片</span>
    </div>

    <p v-if="err" class="ps-err">{{ err }}</p>

    <!-- 拍照还是从相册选,交给用户决定 -->
    <teleport to="body">
      <div v-if="picking" class="ps-pick" @click.self="picking = false">
        <div class="ps-pick-box">
          <button type="button" @click="use('cam')">📷 拍照</button>
          <button type="button" @click="use('lib')">🖼 从相册选</button>
          <button type="button" class="cancel" @click="picking = false">取消</button>
        </div>
      </div>
    </teleport>

    <TripPhotoViewer
      :photos="photos"
      :index="viewing"
      :trip-id="tripId"
      :share-token="shareToken"
      @update:index="viewing = $event"
      @close="viewing = null"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import TripPhotoViewer from '@/components/TripPhotoViewer.vue'
import { photoUrl, uploadPhoto } from '@/utils/tripPhotos'

const props = defineProps({
  photos: { type: Array, default: () => [] },
  canEdit: { type: Boolean, default: false },
  tripId: { type: Number, default: 0 },
  shareToken: { type: String, default: '' },
  label: { type: String, default: '' },
})
const emit = defineEmits(['change'])

const busy = ref(false)
const picking = ref(false)
const camRef = ref(null)
const libRef = ref(null)

function use(kind) {
  ;(kind === 'cam' ? camRef.value : libRef.value)?.click()
}
const err = ref('')
const viewing = ref(null)

function url(sha) {
  return photoUrl({ tripId: props.tripId, shareToken: props.shareToken }, sha)
}

async function onPick(e) {
  const files = [...(e.target.files || [])]
  e.target.value = ''
  picking.value = false
  if (!files.length) return
  busy.value = true
  err.value = ''
  const next = [...props.photos]
  try {
    for (const f of files) {
      const sha = await uploadPhoto(props.tripId, f)
      if (!next.includes(sha)) next.push(sha)   // 同一张图去重,内容寻址天然支持
    }
    emit('change', next)
  } catch (e2) {
    err.value = e2?.response?.data?.error || '上传失败'
  } finally {
    busy.value = false
  }
}

function remove(i) {
  const next = props.photos.filter((_, k) => k !== i)
  emit('change', next)
}
</script>

<style scoped>
.ps-label { font-size: 11px; font-weight: 700; color: var(--color-text-muted); margin-bottom: 5px; }
.ps-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: stretch; }

.ps-thumb {
  position: relative; appearance: none; padding: 0; cursor: pointer;
  width: 76px; height: 76px; border-radius: 10px; overflow: hidden;
  border: 1px solid var(--color-border-light, #e3ddd0); background: var(--color-surface);
}
.ps-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.ps-x {
  position: absolute; right: 3px; top: 3px;
  width: 19px; height: 19px; border-radius: 50%; line-height: 18px; text-align: center;
  background: rgba(0, 0, 0, .55); color: #fff; font-size: 14px; cursor: pointer;
}

.ps-add {
  appearance: none; font: inherit;
  width: 76px; height: 76px; border-radius: 10px; cursor: pointer;
  border: 1.5px dashed var(--trip-accent, var(--color-primary));
  color: var(--trip-accent, var(--color-primary));
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
  background: color-mix(in srgb, var(--trip-accent-weak, #e3ebee) 55%, transparent);
  text-align: center;
}
.ps-add:hover { background: var(--trip-accent-weak, #e3ebee); }
.ps-add.busy { opacity: .6; cursor: default; }
.ps-add-i { font-size: 19px; line-height: 1; }
.ps-add-t { font-size: 10.5px; line-height: 1.25; padding: 0 4px; }
.ps-none { font-size: 12px; color: var(--color-text-muted); align-self: center; }
.ps-err { margin: 6px 0 0; font-size: 12px; color: var(--color-error, #e05a5a); }
</style>

<style>
/* 来源选择浮层 teleport 到 body,不能 scoped */
.ps-pick {
  position: fixed; inset: 0; z-index: 3500;
  background: rgba(20, 26, 30, .45);
  display: flex; align-items: flex-end; justify-content: center;
  padding: 12px; padding-bottom: calc(12px + env(safe-area-inset-bottom, 0px));
}
.ps-pick-box { width: min(420px, 100%); display: flex; flex-direction: column; gap: 8px; }
.ps-pick-box button {
  appearance: none; border: 0; cursor: pointer; font: inherit;
  font-size: 15px; font-weight: 700; padding: 14px;
  border-radius: 14px; background: var(--color-surface, #fff);
  color: var(--color-text-strong, #2A3D45);
}
.ps-pick-box button.cancel { color: var(--color-text-muted); font-weight: 500; }
</style>
