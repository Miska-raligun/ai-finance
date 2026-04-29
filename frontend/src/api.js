import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({ withCredentials: true })

// CSRF token 双通道：cookie + 响应头。
// 内存优先以避免 vite dev proxy 偶发不转发 Set-Cookie 导致 document.cookie
// 拿不到 token；同时把 token 写一份到 sessionStorage 以跨页签 / 刷新生存。
const CSRF_HEADER = 'X-CSRF-Token'
let _csrfToken = ''
try {
  _csrfToken = sessionStorage.getItem('csrf_token') || ''
} catch { /* ignore quota / private mode */ }

function readCookie(name) {
  if (typeof document === 'undefined') return ''
  const m = document.cookie.match(new RegExp('(?:^|;\\s*)' + name + '=([^;]+)'))
  return m ? decodeURIComponent(m[1]) : ''
}

function getCsrfToken() {
  return _csrfToken || readCookie('csrf_token')
}

function rememberCsrfToken(token) {
  if (!token || token === _csrfToken) return
  _csrfToken = token
  try { sessionStorage.setItem('csrf_token', token) } catch { /* ignore */ }
}

// 状态变更请求自动带上 CSRF 头；登录前端点会被后端跳过校验。
api.interceptors.request.use((config) => {
  const method = (config.method || 'get').toUpperCase()
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    const token = getCsrfToken()
    if (token) {
      // axios 1.x 下 config.headers 是 AxiosHeaders 实例，优先用 .set()
      // 以避免 plain assignment 在某些 build 下被忽略。
      if (config.headers && typeof config.headers.set === 'function') {
        config.headers.set(CSRF_HEADER, token)
      } else {
        config.headers = { ...(config.headers || {}), [CSRF_HEADER]: token }
      }
    }
  }
  return config
})

// 全局响应拦截：
//   - 抓取 X-CSRF-Token 头，刷新内存中的 token
//   - 把网络异常 / 鉴权过期 / 频率限制等统一成可读 toast，
//     避免每个调用点都要 try/catch + 自己拼错误文案。
let _redirecting = false

api.interceptors.response.use(
  (resp) => {
    const t = resp?.headers?.[CSRF_HEADER.toLowerCase()] || resp?.headers?.[CSRF_HEADER]
    if (t) rememberCsrfToken(t)
    return resp
  },
  (err) => {
    // 即便是错误响应也可能带新 token（CSRF reject 后下发）
    const t = err?.response?.headers?.[CSRF_HEADER.toLowerCase()]
            || err?.response?.headers?.[CSRF_HEADER]
    if (t) rememberCsrfToken(t)

    const status = err?.response?.status
    const data = err?.response?.data
    const serverMsg = (data && (data.message || data.error)) || ''

    if (status === 401) {
      // session 过期：清栈跳登录。短时间内多次 401 只跳一次。
      if (!_redirecting && typeof window !== 'undefined') {
        const onLogin = window.location.pathname.startsWith('/login')
        if (!onLogin) {
          _redirecting = true
          ElMessage.warning('登录已过期，请重新登录')
          window.location.replace('/login')
        }
      }
    } else if (status === 429) {
      ElMessage.warning(serverMsg || '请求过于频繁，请稍后再试')
    } else if (status >= 500) {
      ElMessage.error(serverMsg || '服务器异常，请稍后重试')
    } else if (status >= 400) {
      // 4xx 业务错误：默认 toast，但允许调用方通过 { silent: true } 自行处理
      if (!err?.config?.silent) {
        ElMessage.error(serverMsg || `请求失败 (${status})`)
      }
    } else if (err?.code === 'ERR_NETWORK' || err?.message === 'Network Error') {
      ElMessage.error('网络异常，请检查后端是否启动')
    }

    return Promise.reject(err)
  }
)

// 让 main.js 中的 fetch monkey patch 也能复用同一份 token 状态。
export { getCsrfToken, rememberCsrfToken, CSRF_HEADER }
export default api
