// src/main.js
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
// 与 axios 共享 CSRF token 状态：cookie 通道在某些 vite proxy 配置下会被
// 吞掉，header 通道是必传的，统一从 api.js 维护的内存 token 读。
import { getCsrfToken, rememberCsrfToken, CSRF_HEADER } from '@/api'

const _origFetch = window.fetch.bind(window)
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
  }
  const resp = await _origFetch(input, init)
  // 抓 X-CSRF-Token 头同步内存 token。即使 vite dev proxy 不透传 Set-Cookie，
  // header 也一定能传过来，确保后续 POST 不会因 cookie 缺失被 CSRF 拦截。
  try {
    const t = resp.headers && resp.headers.get(CSRF_HEADER)
    if (t) rememberCsrfToken(t)
  } catch { /* opaque response */ }
  return resp
}

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(ElementPlus)

app.mount('#app')
