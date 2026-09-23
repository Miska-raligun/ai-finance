/** 生成「在地图里打开」的链接。
 *
 * 为什么不内嵌地图:整站 CSP 是 default-src 'self',嵌入第三方瓦片/SDK 会被挡,
 * 而且会把行程坐标发给第三方。外链是顶层导航,不受 CSP 约束,也不加载任何外部资源。
 *
 * 坐标优先(落点精确),没有坐标就退回「名称 + 地址」搜索——多数行程只填了酒店名。
 * 苹果设备走 Apple Maps(iOS 上直接唤起 App),其余走 Google Maps
 * (Android 上同样唤起 App,桌面端开网页)。
 */
export function mapUrl({ lat, lng, name, addr } = {}) {
  const hasCoord = Number.isFinite(Number(lat)) && Number.isFinite(Number(lng))
  const label = [name, addr].filter(Boolean).join(' ').trim()
  if (!hasCoord && !label) return ''

  const apple = typeof navigator !== 'undefined'
    && /iPhone|iPad|iPod|Macintosh/.test(navigator.userAgent || '')

  if (hasCoord) {
    const ll = `${Number(lat)},${Number(lng)}`
    // Apple 用 ll 定位 + q 显示名字;Google 用 query 直接吃 "lat,lng"
    return apple
      ? `https://maps.apple.com/?ll=${ll}${label ? `&q=${encodeURIComponent(label)}` : ''}`
      : `https://www.google.com/maps/search/?api=1&query=${ll}`
  }
  const q = encodeURIComponent(label)
  return apple
    ? `https://maps.apple.com/?q=${q}`
    : `https://www.google.com/maps/search/?api=1&query=${q}`
}
