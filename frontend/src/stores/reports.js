import { defineStore } from 'pinia'
import api from '@/api'

/**
 * 月度报告 Pinia store。
 */
export const useReportsStore = defineStore('reports', {
  state: () => ({
    list: [],
    current: null,
    loading: false,
    generating: false,
  }),

  actions: {
    async fetchList() {
      const res = await api.get('/api/reports')
      this.list = res.data || []
    },

    async fetchOne(period) {
      this.loading = true
      try {
        const res = await api.get(`/api/reports/${period}`)
        this.current = res.data
        return res.data
      } finally {
        this.loading = false
      }
    },

    async generate(month, llm = null) {
      this.generating = true
      try {
        const url = month ? `/api/reports/generate?month=${month}` : '/api/reports/generate'
        const res = await api.post(url, { llm })
        this.current = res.data
        await this.fetchList()
        return res.data
      } finally {
        this.generating = false
      }
    },

    async remove(period) {
      await api.delete(`/api/reports/${period}`)
      if (this.current?.period === period) this.current = null
      await this.fetchList()
    },
  },
})
