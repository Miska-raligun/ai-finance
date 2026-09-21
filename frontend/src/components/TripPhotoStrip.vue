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
      <label v-if="canEdit" class="ps-add" :class="{ busy }">
        <input
          type="file"
          accept="image/*"
          capture="environment"
          multiple
          hidden
          :disabled="busy"
          @change="onPick"
        >
        <span v-if="busy" class="ps-add-t">上传中…</span>
        <template v-else>
          <span class="ps-add-i">＋</span>
          <span class="ps-add-t">{{ photos.length ? '再拍一张' : '拍照 / 选图' }}</span>
        </template>
      </label>

      <span v-else-if="!photos.length" class="ps-none">还没有照片</span>
    </div>

    <p v-if="err" class="ps-err">{{ err }}</p>

    <!-- 看大图 -->
    <teleport to="body">
      <div v-if="viewing !== null" class="ps-view" @click.self="viewing = null">
        <button class="ps-view-x" aria-label="关闭" @click="viewing = null">×</button>
        <button
          v-if="photos.length > 1"
          class="ps-view-nav prev"
          aria-label="上一张"
          @click.stop="step(-1)"
        >‹</button>
        <img :src="url(photos[viewing])" alt="">
        <button
          v-if="photos.length > 1"
          class="ps-view-nav next"
          aria-label="下一张"
          @click.stop="step(1)"
        >›</button>
        <div v-if="photos.length > 1" class="ps-view-n">{{ viewing + 1 }} / {{ photos.length }}</div>
      </div>
    </teleport>
  </div>
</template>

<script setup>
import { ref } from 'vue'
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
const err = ref('')
const viewing = ref(null)

function url(sha) {
  return photoUrl({ tripId: props.tripId, shareToken: props.shareToken }, sha)
}

function step(d) {
  const n = props.photos.length
  viewing.value = (viewing.value + d + n) % n
}

async function onPick(e) {
  const files = [...(e.target.files || [])]
  e.target.value = ''
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
/* 大图浏览 teleport 到 body,不能 scoped */
.ps-view {
  position: fixed; inset: 0; z-index: 3200;
  background: rgba(10, 14, 16, .9);
  display: flex; align-items: center; justify-content: center;
}
.ps-view img { max-width: 94vw; max-height: 88vh; border-radius: 8px; display: block; }
.ps-view-x {
  position: absolute; right: 14px; top: 14px; width: 34px; height: 34px;
  border: 0; border-radius: 50%; background: rgba(255, 255, 255, .85);
  font-size: 21px; line-height: 1; cursor: pointer; color: #222;
}
.ps-view-nav {
  position: absolute; top: 50%; transform: translateY(-50%);
  width: 42px; height: 58px; border: 0; border-radius: 10px;
  background: rgba(255, 255, 255, .16); color: #fff; font-size: 27px; cursor: pointer;
}
.ps-view-nav.prev { left: 10px; }
.ps-view-nav.next { right: 10px; }
.ps-view-n {
  position: absolute; bottom: 16px; left: 50%; transform: translateX(-50%);
  color: rgba(255, 255, 255, .8); font-size: 12px; font-variant-numeric: tabular-nums;
}
</style>
