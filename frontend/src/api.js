import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({ withCredentials: true })

// 全局响应拦截：把网络异常 / 鉴权过期 / 频率限制等统一成可读 toast，
// 避免每个调用点都要 try/catch + 自己拼错误文案。
let _redirecting = false

api.interceptors.response.use(
  (resp) => resp,
  (err) => {
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

export default api
