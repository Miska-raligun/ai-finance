import { defineStore } from 'pinia'
import api from '@/api'
import { runAiJob } from '@/utils/aiJobs'

/**
 * 财务体检 Pinia store。
 * - compute：让 AI 基于真实数据打分（0-100）+ 四维拆解 + 报告，并存档。
 * - fetchCurrent：取某月已存档结果（不触发 LLM）。
 * - fetchHistory：历史分数序列，画趋势折线。
 */
export const useCheckupStore = defineStore('checkup', {
  state: () => ({
    current: null,
    history: [],
    computing: false,
    loading: false,
  }),

  actions: {
    async fetchCurrent(month) {
      this.loading = true
      try {
        const url = month ? `/api/checkup/current?month=${month}` : '/api/checkup/current'
        const res = await api.get(url)
        this.current = res.data && Object.keys(res.data).length ? res.data : null
        return this.current
      } finally {
        this.loading = false
      }
    },

    async compute(month, llm = null, { signal } = {}) {
      this.computing = true
      try {
        const url = month ? `/api/checkup/compute?month=${month}` : '/api/checkup/compute'
        // 后端改成异步了:POST 只排队,结果轮询取。同步的话连接要挂几分钟,
        // 会踩 nginx 超时 / 熔断和 waitress 线程占满。
        const data = await runAiJob(url, { llm }, { signal })
        this.current = data
        await this.fetchHistory()
        return data
      } finally {
        this.computing = false
      }
    },

    async fetchHistory(months = 12) {
      const res = await api.get(`/api/checkup/history?months=${months}`)
      this.history = res.data || []
      return this.history
    },
  },
})
