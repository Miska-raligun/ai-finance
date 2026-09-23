/** WGS-84 → GCJ-02(火星坐标)。
 *
 *  高德的瓦片是 GCJ-02 的。行程里的经纬度是 WGS-84(手机定位、维基、
 *  Google 都是这个),直接丢到高德底图上,**在中国境内**会偏出几百米——
 *  酒店会落到隔壁街区。境外两者一致,所以只在境内做偏移。
 *
 *  境内判定用的是常见的粗略外接框:港澳台在框内但高德对它们用的是 WGS-84,
 *  这是这套算法公认的近似,不追求那几个点的精确。
 */
const PI = Math.PI
const A = 6378245.0              // 克拉索夫斯基椭球长半轴
const EE = 0.00669342162296594323

function outOfChina(lat, lng) {
  return lng < 72.004 || lng > 137.8347 || lat < 0.8293 || lat > 55.8271
}

function tLat(x, y) {
  let ret = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x))
  ret += (20 * Math.sin(6 * x * PI) + 20 * Math.sin(2 * x * PI)) * 2 / 3
  ret += (20 * Math.sin(y * PI) + 40 * Math.sin(y / 3 * PI)) * 2 / 3
  ret += (160 * Math.sin(y / 12 * PI) + 320 * Math.sin(y * PI / 30)) * 2 / 3
  return ret
}

function tLng(x, y) {
  let ret = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x))
  ret += (20 * Math.sin(6 * x * PI) + 20 * Math.sin(2 * x * PI)) * 2 / 3
  ret += (20 * Math.sin(x * PI) + 40 * Math.sin(x / 3 * PI)) * 2 / 3
  ret += (150 * Math.sin(x / 12 * PI) + 300 * Math.sin(x / 30 * PI)) * 2 / 3
  return ret
}

/** @returns {[number, number]} [lat, lng] */
export function wgs2gcj(lat, lng) {
  if (outOfChina(lat, lng)) return [lat, lng]
  const x = lng - 105.0, y = lat - 35.0
  let dLat = tLat(x, y)
  let dLng = tLng(x, y)
  const radLat = lat / 180.0 * PI
  let magic = Math.sin(radLat)
  magic = 1 - EE * magic * magic
  const sqrtMagic = Math.sqrt(magic)
  dLat = (dLat * 180.0) / ((A * (1 - EE)) / (magic * sqrtMagic) * PI)
  dLng = (dLng * 180.0) / (A / sqrtMagic * Math.cos(radLat) * PI)
  return [lat + dLat, lng + dLng]
}

/** GCJ-02 → WGS-84。
 *
 *  没有解析逆变换,用迭代逼近:把当前猜测正向转一次,拿偏差反推回去。
 *  三四轮就收敛到厘米级,够用。切换底图(高德是 GCJ-02、OSM 是 WGS-84)时
 *  要把地图中心换算过去,否则一换图整幅会跳几百米。
 * @returns {[number, number]} [lat, lng]
 */
export function gcj2wgs(lat, lng) {
  if (outOfChina(lat, lng)) return [lat, lng]
  let wLat = lat, wLng = lng
  for (let i = 0; i < 5; i++) {
    const [gLat, gLng] = wgs2gcj(wLat, wLng)
    const dLat = gLat - lat, dLng = gLng - lng
    if (Math.abs(dLat) < 1e-9 && Math.abs(dLng) < 1e-9) break
    wLat -= dLat
    wLng -= dLng
  }
  return [wLat, wLng]
}
