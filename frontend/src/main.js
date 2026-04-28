// src/main.js
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'

// 全局拦截 window.fetch：补上凭证 + CSRF token，避免散落的 fetch() 调用被
// 后端 CSRF 中间件拒绝。axios 调用走 api.js 的拦截器。
const _origFetch = window.fetch.bind(window)
function _csrfToken() {
  const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}
window.fetch = (input, init = {}) => {
  const url = typeof input === 'string' ? input : input.url
  if (url && url.startsWith('/api/')) {
    init.credentials = init.credentials || 'include'
    const method = (init.method || 'GET').toUpperCase()
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
      const token = _csrfToken()
      if (token) {
        const headers = new Headers(init.headers || {})
        if (!headers.has('X-CSRF-Token')) headers.set('X-CSRF-Token', token)
        init.headers = headers
      }
    }
  }
  return _origFetch(input, init)
}

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(ElementPlus)

app.mount('#app')
