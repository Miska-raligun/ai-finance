/** 行程照片的共用逻辑:URL 拼装、旧字段兼容、上传前压缩。
 *
 *  停留点在 detail_json 里只存 sha,不存 URL——URL 前缀在私有页
 *  (/api/trips/<id>/photos/)和公开分享页(/api/public/trips/<token>/photos/)
 *  是两套,存死了分享出去就取不到。
 */

/** @param {{tripId?: number, shareToken?: string}} ctx
 *  @param {{thumb?: boolean}} [opt] 缩略图:格子、封面这种小位置用它,
 *    76px 的格子没必要拉 1280px 的原图。旧照片没有缩略图,服务端会回落到原图。 */
export function photoUrl(ctx, sha, opt = {}) {
  if (!sha) return ''
  const q = opt.thumb ? '?s=t' : ''
  if (ctx?.shareToken) {
    return `/api/public/trips/${encodeURIComponent(ctx.shareToken)}/photos/${sha}${q}`
  }
  return ctx?.tripId ? `/api/trips/${ctx.tripId}/photos/${sha}${q}` : ''
}

/** 一个停留点的照片列表。photos 是数组,photo 是最早的单张字段,两者都认。 */
export function photoList(stop) {
  if (!stop) return []
  if (Array.isArray(stop.photos)) return stop.photos.filter(Boolean)
  return stop.photo ? [stop.photo] : []
}

const FULL_MAX = 1280
const THUMB_MAX = 480     // 够格子(76px)和地图弹窗封面(~400px 宽)在 2x 屏上用

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

/** 上传前在浏览器里缩到 1280px 的 JPEG,顺手出一张 480px 的缩略图。
 *  手机直出动辄 5MB,服务端单请求上限 8MB;这些图只是留念用的配图,
 *  1280 足够,传得也快——在外面用移动网络传照片这点很实在。
 *  只解码一次:缩略图从缩好的那张再缩,不再碰原图。 */
export async function shrink(file) {
  let bmp
  try {
    bmp = await createImageBitmap(file)
  } catch {
    // 典型是安卓/电脑上的 HEIC:浏览器解不开,给句人话而不是"上传失败"
    throw new Error('这张图浏览器读不了(可能是 HEIC 格式),换成 JPG 再试')
  }
  const full = scaled(bmp, bmp.width, bmp.height, FULL_MAX)
  bmp.close?.()
  const thumb = scaled(full, full.width, full.height, THUMB_MAX)
  const [image, thumbBlob] = await Promise.all([toJpeg(full, 0.82), toJpeg(thumb, 0.75)])
  return { image, thumb: thumbBlob }
}

/** @returns {Promise<string>} sha256 */
export async function uploadPhoto(tripId, file) {
  const { image, thumb } = await shrink(file)
  const form = new FormData()
  form.append('image', image, 'photo.jpg')
  form.append('thumb', thumb, 'thumb.jpg')
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
