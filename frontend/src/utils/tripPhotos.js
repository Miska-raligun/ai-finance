/** 行程照片的共用逻辑:URL 拼装、旧字段兼容、上传前压缩。
 *
 *  停留点在 detail_json 里只存 sha,不存 URL——URL 前缀在私有页
 *  (/api/trips/<id>/photos/)和公开分享页(/api/public/trips/<token>/photos/)
 *  是两套,存死了分享出去就取不到。
 */

/** @param {{tripId?: number, shareToken?: string}} ctx */
export function photoUrl(ctx, sha) {
  if (!sha) return ''
  if (ctx?.shareToken) {
    return `/api/public/trips/${encodeURIComponent(ctx.shareToken)}/photos/${sha}`
  }
  return ctx?.tripId ? `/api/trips/${ctx.tripId}/photos/${sha}` : ''
}

/** 一个停留点的照片列表。photos 是数组,photo 是最早的单张字段,两者都认。 */
export function photoList(stop) {
  if (!stop) return []
  if (Array.isArray(stop.photos)) return stop.photos.filter(Boolean)
  return stop.photo ? [stop.photo] : []
}

// 服务端只存这一份显示用的图,不留原图。和 backend/services/trip_photos.py
// 的 DISPLAY_MAX 保持一致——超过的话服务端会再缩一次,白白多传
const DISPLAY_MAX = 800
const QUALITY = 0.75

function scaled(src, w0, h0, max) {
  const k = Math.min(1, max / Math.max(w0, h0))
  const c = document.createElement('canvas')
  c.width = Math.round(w0 * k); c.height = Math.round(h0 * k)
  c.getContext('2d').drawImage(src, 0, 0, c.width, c.height)
  return c
}

function toJpeg(canvas, quality) {
  // toBlob 而不是 toDataURL:编码不卡主线程,也省掉 base64 那 33% 的体积
  return new Promise((resolve, reject) => {
    canvas.toBlob(b => (b ? resolve(b) : reject(new Error('图片编码失败'))), 'image/jpeg', quality)
  })
}

/** 上传前在浏览器里缩成长边 800px 的 JPEG,只传这一张。
 *  手机直出动辄 5MB;这些图只是留念用的配图,800 在手机上看足够,
 *  一张一两百 KB 以内,在外面用移动网络也传得动。
 *  canvas 重新编码还会顺带去掉 EXIF(里面可能有拍摄地的 GPS)。 */
export async function shrink(file) {
  let bmp
  try {
    bmp = await createImageBitmap(file)
  } catch {
    // 典型是安卓/电脑上的 HEIC:浏览器解不开,给句人话而不是"上传失败"
    throw new Error('这张图浏览器读不了(可能是 HEIC 格式),换成 JPG 再试')
  }
  const canvas = scaled(bmp, bmp.width, bmp.height, DISPLAY_MAX)
  bmp.close?.()
  return toJpeg(canvas, QUALITY)
}

/** @returns {Promise<string>} sha256 */
export async function uploadPhoto(tripId, file) {
  const form = new FormData()
  form.append('image', await shrink(file), 'photo.jpg')
  const { default: api } = await import('@/api')
  const res = await api.post(`/api/trips/${tripId}/photos`, form)
  return res.data.sha256
}

/** 一次传多张:两张同时在路上,一张压缩的时候另一张在上传,
 *  不再是"压一张传一张"地排队。结果按选图顺序返回,失败的那张记 null。
 *  @param {(done: number, total: number) => void} [onProgress] */
export async function uploadPhotos(tripId, files, onProgress, concurrency = 2) {
  const out = new Array(files.length).fill(null)
  let next = 0, done = 0, firstErr = null
  onProgress?.(0, files.length)
  async function worker() {
    while (next < files.length) {
      const i = next++
      try {
        out[i] = await uploadPhoto(tripId, files[i])
      } catch (e) {
        firstErr ??= e
      }
      onProgress?.(++done, files.length)
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, files.length) }, worker))
  return { shas: out.filter(Boolean), error: firstErr }
}

/** 上传失败时给用户看的那句话:服务端的 error 优先,其次是本地抛出的说明 */
export function uploadErrorText(e) {
  if (e?.response) return e.response.data?.error || `上传失败 (${e.response.status})`
  return e?.message || '上传失败'
}
