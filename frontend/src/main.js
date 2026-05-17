// src/main.js
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
// Animal Island 主题：紧跟 element-plus 默认样式之后加载以覆盖
import '@/styles/animal-theme.css'
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
app.use(ElementPlus)

app.mount('#app')
