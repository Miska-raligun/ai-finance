/** 部署新版本后,已经打开的页面还是上一版:页面里各页面的分包、样式都按上一版
 *  的文件名去取,而那些文件随新版本一起被删掉了。服务器对取不到的文件回的是
 *  首页 HTML(SPA 回落),浏览器把它当样式表静默丢掉——页面内容还在,框架全散,
 *  而且不报任何错。
 *
 *  办法:切换页面时看一眼服务器上的 index.html 引用的入口文件名和当前页面的
 *  是否一致;不一致说明已经换了版本,这次跳转改成整页加载。
 *  只在生产构建里生效(开发服务器没有带 hash 的入口文件)。
 */

const CHECK_EVERY_MS = 10_000     // 十秒内最多问一次;index.html 很小,问一次几乎没成本
const CHECK_TIMEOUT_MS = 1500     // 网络慢就不等了,照常切页面

let lastCheck = 0
let stale = false

function entryOf(html) {
  const m = html.match(/\/assets\/index-[\w-]+\.js/)
  return m ? m[0] : ''
}

const current = typeof document === 'undefined' ? ''
  : entryOf([...document.scripts].map(s => s.getAttribute('src') || '').join(' '))

async function checkNow() {
  lastCheck = Date.now()
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), CHECK_TIMEOUT_MS)
  try {
    const res = await fetch('/', { cache: 'no-store', signal: ctrl.signal })
    const latest = entryOf(await res.text())
    if (latest && latest !== current) stale = true
  } catch { /* 网络问题不算换版本 */ } finally {
    clearTimeout(timer)
  }
}

/** 挂到 router 上:发现版本变了,就把这次跳转换成整页加载 */
export function installStaleBuildGuard(router) {
  if (!current) return                 // 开发模式或认不出入口文件:什么都不做
  router.beforeEach(async (to, from) => {
    if (!from.matched.length) return true          // 首次进入本来就是整页加载
    if (!stale && Date.now() - lastCheck > CHECK_EVERY_MS) await checkNow()
    if (stale) {
      window.location.assign(to.fullPath)
      return false
    }
    return true
  })
  // 页面从后台切回来时提前问一次,下次切页面就不用等
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && Date.now() - lastCheck > CHECK_EVERY_MS) checkNow()
  })
}
