<!-- components/TripPhotoViewer.vue — 看大图。手机上可左右滑动翻页。 -->
<template>
  <teleport to="body">
    <div
      v-if="index !== null"
      class="pv"
      @click.self="$emit('close')"
      @touchstart.passive="onStart"
      @touchend.passive="onEnd"
    >
      <button class="pv-x" aria-label="关闭" @click="$emit('close')">×</button>
      <img :src="url(photos[index])" alt="">
      <template v-if="photos.length > 1">
        <button class="pv-nav prev" aria-label="上一张" @click.stop="step(-1)">‹</button>
        <button class="pv-nav next" aria-label="下一张" @click.stop="step(1)">›</button>
        <div class="pv-n">{{ index + 1 }} / {{ photos.length }}</div>
      </template>
    </div>
  </teleport>
</template>

<script setup>
import { photoUrl } from '@/utils/tripPhotos'

const props = defineProps({
  photos: { type: Array, default: () => [] },
  index: { type: Number, default: null },
  tripId: { type: Number, default: 0 },
  shareToken: { type: String, default: '' },
})
const emit = defineEmits(['close', 'update:index'])

function url(sha) {
  return photoUrl({ tripId: props.tripId, shareToken: props.shareToken }, sha)
}

function step(d) {
  const n = props.photos.length
  if (!n) return
  emit('update:index', (props.index + d + n) % n)
}

// 手机上没有鼠标,左右滑更自然
let x0 = null
function onStart(e) { x0 = e.changedTouches?.[0]?.clientX ?? null }
function onEnd(e) {
  if (x0 === null) return
  const dx = (e.changedTouches?.[0]?.clientX ?? x0) - x0
  x0 = null
  if (Math.abs(dx) > 48) step(dx < 0 ? 1 : -1)
}
</script>

<style>
.pv {
  position: fixed; inset: 0; z-index: 3400;
  background: rgba(10, 14, 16, .93);
  display: flex; align-items: center; justify-content: center;
}
.pv img { max-width: 96vw; max-height: 86vh; border-radius: 8px; display: block; }
.pv-x {
  position: absolute; right: 14px; top: 14px; width: 36px; height: 36px;
  border: 0; border-radius: 50%; background: rgba(255, 255, 255, .88);
  font-size: 22px; line-height: 1; cursor: pointer; color: #222;
}
.pv-nav {
  position: absolute; top: 50%; transform: translateY(-50%);
  width: 44px; height: 60px; border: 0; border-radius: 10px;
  background: rgba(255, 255, 255, .16); color: #fff; font-size: 28px; cursor: pointer;
}
.pv-nav.prev { left: 10px; }
.pv-nav.next { right: 10px; }
.pv-n {
  position: absolute; bottom: 18px; left: 50%; transform: translateX(-50%);
  color: rgba(255, 255, 255, .82); font-size: 12px; font-variant-numeric: tabular-nums;
}
@media (max-width: 560px) {
  .pv-nav { display: none; }     /* 窄屏靠滑动,按钮反而挡图 */
}
</style>
