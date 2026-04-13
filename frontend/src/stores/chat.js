// src/stores/chat.js
import { defineStore } from 'pinia'
import api from '@/api'

/**
 * 聊天消息持久化 store。
 *
 * - 首次进入 ChatView 时从后端 /api/chat/history 加载历史消息
 * - 后续页面切换（keep-alive）直接使用内存中的消息列表
 * - 切换用户时调用 reset() 清空缓存
 */
export const useChatStore = defineStore('chat', {
  state: () => ({
    messages: [],
    _loaded: false,
  }),

  actions: {
    async loadHistory() {
      if (this._loaded) return
      try {
        const res = await api.get('/api/chat/history')
        if (res.data && res.data.length) {
          this.messages = res.data.map(m => ({
            sender: m.role === 'user' ? 'user' : 'assistant',
            content: m.content,
          }))
        }
      } catch {
        // 首次加载失败不影响使用
      }
      this._loaded = true
    },

    pushMessage(msg) {
      this.messages.push(msg)
    },

    reset() {
      this.messages = []
      this._loaded = false
    },
  },
})
