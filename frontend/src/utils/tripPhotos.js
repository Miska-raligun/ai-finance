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

/** 上传前在浏览器里缩到 1280px 的 JPEG。
 *  手机直出动辄 5MB,服务端单请求上限 8MB;这些图只是留念用的配图,
 *  1280 足够,传得也快——在外面用移动网络传照片这点很实在。 */
export async function shrink(file, max = 1280, quality = 0.82) {
  const bmp = await createImageBitmap(file)
  const k = Math.min(1, max / Math.max(bmp.width, bmp.height))
  const w = Math.round(bmp.width * k), h = Math.round(bmp.height * k)
  const c = document.createElement('canvas')
  c.width = w; c.height = h
  c.getContext('2d').drawImage(bmp, 0, 0, w, h)
  bmp.close?.()
  return c.toDataURL('image/jpeg', quality)
}

/** @returns {Promise<string>} sha256 */
export async function uploadPhoto(tripId, file) {
  const dataUrl = await shrink(file)
  const { default: api } = await import('@/api')
  const res = await api.post(`/api/trips/${tripId}/photos`, { image: dataUrl })
  return res.data.sha256
}
