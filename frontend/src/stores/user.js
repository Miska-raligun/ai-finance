// src/stores/user.js
import { defineStore } from 'pinia'
import api from '@/api'

/**
 * 统一管理用户身份 + LLM 配置，替代分散的 localStorage 读写。
 * - username / isAdmin：从 /api/me 获取，登录时刷新，登出时清空
 * - llmConfig：LLM 自定义配置，null 表示使用后端默认
 */
export const useUserStore = defineStore('user', {
  state: () => ({
    username: localStorage.getItem('username') || '',
    isAdmin: localStorage.getItem('is_admin') === '1',
    llmConfig: _loadLlmConfig(),
    _meFetched: false,
  }),

  getters: {
    isLoggedIn: (state) => !!state.username,
    userInitial: (state) => state.username ? state.username.slice(0, 1).toUpperCase() : '',
    /** 返回用于提交给 /api/chat 的 llm 对象；默认时为 null */
    llmPayload: (state) => {
      if (!state.llmConfig || state.llmConfig === 'default') return null
      return state.llmConfig
    },
  },

  actions: {
    /** 从 /api/me 拉取最新身份并同步到 localStorage，供路由守卫/侧边栏使用 */
    async fetchMe() {
      try {
        const res = await api.get('/api/me')
        this.username = res.data.username || ''
        this.isAdmin = !!res.data.is_admin
        if (this.username) {
          localStorage.setItem('username', this.username)
        } else {
          localStorage.removeItem('username')
        }
        if (this.isAdmin) {
          localStorage.setItem('is_admin', '1')
        } else {
          localStorage.removeItem('is_admin')
        }
      } catch {
        this.username = ''
        this.isAdmin = false
        localStorage.removeItem('username')
        localStorage.removeItem('is_admin')
      }
      this._meFetched = true
    },

    /** 登录成功后调用（由 LoginView 在拿到 is_admin 后直接写入） */
    setIdentity({ username, isAdmin }) {
      this.username = username || ''
      this.isAdmin = !!isAdmin
      if (this.username) {
        localStorage.setItem('username', this.username)
      } else {
        localStorage.removeItem('username')
      }
      if (this.isAdmin) {
        localStorage.setItem('is_admin', '1')
      } else {
        localStorage.removeItem('is_admin')
      }
    },

    /** 登出：清理本地状态（后端 /api/logout 由调用方处理） */
    async logout() {
      try {
        await fetch('/api/logout', { method: 'POST', credentials: 'include' })
      } catch { /* 网络错误也继续清理本地 */ }
      this.username = ''
      this.isAdmin = false
      localStorage.removeItem('username')
      localStorage.removeItem('is_admin')
    },

    /** 保存自定义 LLM 配置 */
    async saveLlmConfig({ url, apikey, model, persona }) {
      const payload = { url, apikey, model, persona }
      await fetch('/api/llm_config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      this.llmConfig = payload
      localStorage.setItem('llmConfig', JSON.stringify(payload))
    },

    /** 使用系统默认 LLM 配置 */
    async useDefaultLlm() {
      await fetch('/api/llm_config', { method: 'DELETE', credentials: 'include' })
      this.llmConfig = 'default'
      localStorage.setItem('llmConfig', 'default')
    },

    /** 是否需要弹出 LLM 配置对话框（首次使用） */
    needLlmConfig() {
      return !localStorage.getItem('llmConfig')
    },
  },
})

function _loadLlmConfig() {
  const raw = localStorage.getItem('llmConfig')
  if (!raw) return null
  if (raw === 'default') return 'default'
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}
