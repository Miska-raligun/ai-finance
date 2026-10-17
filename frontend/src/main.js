import '@/styles/fonts.css'
// src/main.js
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
// Element Plus 改为按需引入：模板里的 <el-*> 标签由 unplugin-vue-components 在编译期
// 自动注入对应组件 + CSS；命令式 API（ElMessage / ElMessageBox / ElNotification / ElLoading）
// 各文件按需 `import { ElMessage } from 'element-plus'` 显式引入即可，
// 但它们的 CSS 不会被自动注入——必须在这里手动 import 一次。
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/notification/style/css'
import 'element-plus/es/components/loading/style/css'
// Animal Island 主题：在 EP 注入的样式之后加载以覆盖。
import '@/styles/animal-theme.css'
// 主题色板预设：暗色 + 四季
import '@/styles/themes.css'

// 启动时立即应用保存的主题（先于 Vue mount），避免页面短暂闪烁默认色
;(function _bootTheme() {
  try {
    const auto = localStorage.getItem('theme_auto') === '1'
    let theme
    if (auto) {
      const m = new Date().getMonth() + 1
      theme = m >= 3 && m <= 5 ? 'spring'
            : m >= 6 && m <= 8 ? 'summer'
            : m >= 9 && m <= 11 ? 'autumn'
            : 'winter'
    } else {
      theme = localStorage.getItem('theme') || 'default'
    }
    if (theme && theme !== 'default') {
      document.body.setAttribute('data-theme', theme)
    }
  } catch { /* localStorage 不可用时降级为默认 */ }
})()
// 部署新版本后，已经打开的页面（或缓存里的旧 index）还指着上一版的分包文件名，
// 那些文件已被删掉：样式表取不到时页面只剩内容、框架全散。Vite 在分包 / 样式
// 加载失败时会发 vite:preloadError，这里整页刷新一次换成新版本。
// 30 秒内只刷一次，免得服务器真出问题时陷入无限刷新。
window.addEventListener('vite:preloadError', (event) => {
  try {
    const last = Number(sessionStorage.getItem('chunk_reload_at') || 0)
    if (Date.now() - last < 30_000) return
    sessionStorage.setItem('chunk_reload_at', String(Date.now()))
  } catch { /* sessionStorage 不可用：照样刷新一次 */ }
  event.preventDefault()
  window.location.reload()
})
// ECharts 全局主题注册：让所有 echarts 实例默认走动森配色
import * as echarts from 'echarts/core'
import { ANIMAL_ECHARTS_THEME } from '@/echarts-theme'
echarts.registerTheme('animal', ANIMAL_ECHARTS_THEME)
// 与 axios 共享 CSRF token 状态：cookie 通道在某些 vite proxy 配置下会被
// 吞掉，header 通道是必传的，统一从 api.js 维护的内存 token 读。
import { getCsrfToken, rememberCsrfToken, CSRF_HEADER } from '@/api'

const _origFetch = window.fetch.bind(window)

async function _doFetch(input, init) {
  const resp = await _origFetch(input, init)
  // 抓 X-CSRF-Token 头同步内存 token。即使 vite dev proxy 不透传 Set-Cookie，
  // header 也一定能传过来，确保后续 POST 不会因 cookie 缺失被 CSRF 拦截。
  try {
    const t = resp.headers && resp.headers.get(CSRF_HEADER)
    if (t) rememberCsrfToken(t)
  } catch { /* opaque response */ }
  return resp
}

window.fetch = async (input, init = {}) => {
  const url = typeof input === 'string' ? input : input.url
  if (url && url.startsWith('/api/')) {
    init.credentials = init.credentials || 'include'
    const method = (init.method || 'GET').toUpperCase()
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
      const token = getCsrfToken()
      if (token) {
        const headers = new Headers(init.headers || {})
        if (!headers.has(CSRF_HEADER)) headers.set(CSRF_HEADER, token)
        init.headers = headers
      }
    }
    // 切回前台 / wifi 抖动时一次 TCP 失败就静默重试一次，避免页面 toast 风暴
    try {
      return await _doFetch(input, init)
    } catch (e) {
      if (e instanceof TypeError) {
        await new Promise(r => setTimeout(r, 800))
        return await _doFetch(input, init)
      }
      throw e
    }
  }
  return _doFetch(input, init)
}

const app = createApp(App)

app.use(createPinia())
app.use(router)
// 不再 app.use(ElementPlus) —— 按需引入时不需要全局注册。

app.mount('#app')
