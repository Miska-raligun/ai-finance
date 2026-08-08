import { defineStore } from 'pinia'
import api from '@/api'
import bus from '@/event-bus'

/**
 * 月度报告 Pinia store。
 *
 * 报告生成是异步任务（LLM 经常 90~180s）：
 *   1. POST /api/reports/generate 立即返回 status: pending
 *   2. 轮询 GET /api/reports/<period>/status
 *   3. status=done 后拉详情；status=failed 抛错
 */
export const useReportsStore = defineStore('reports', {
  state: () => ({
    list: [],
    current: null,
    loading: false,
    generating: false,
    /** 'pending' | 'running' | 'done' | 'failed' | '' */
    genStatus: '',
    genError: '',
    /** 本月回顾卡片数据（亮点 + 文案），按月即时拉取 */
    recap: null,
    recapLoading: false,
    /** 数据失效标记：其他页改账后置 true，ReportsView onActivated 检查并刷新。 */
    stale: false,
  }),

  actions: {
    /** 订阅一次跨页数据变更（store 实例只装载一次，handler 不重复）。 */
    _ensureBusSub() {
      if (this._busSubscribed) return
      this._busSubscribed = true
      const mark = () => { this.stale = true }
      bus.on('data:records', mark)
      bus.on('data:income', mark)
      bus.on('data:budgets', mark)
    },

    async fetchList() {
      this._ensureBusSub()
      const res = await api.get('/api/reports')
      this.list = res.data || []
      this.stale = false
    },

    async fetchRecap(month) {
      this._ensureBusSub()
      this.recapLoading = true
      try {
        const url = month ? `/api/reports/recap?month=${month}` : '/api/reports/recap'
        const res = await api.get(url)
        this.recap = res.data
        this.stale = false
        return res.data
      } finally {
        this.recapLoading = false
      }
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

    async _pollStatus(period, { intervalMs = 3000, timeoutMs = 5 * 60 * 1000 } = {}) {
      const start = Date.now()
      while (Date.now() - start < timeoutMs) {
        await new Promise(r => setTimeout(r, intervalMs))
        try {
          const res = await api.get(`/api/reports/${period}/status`, { silent: true })
          this.genStatus = res.data?.status || ''
          if (this.genStatus === 'done') return 'done'
          if (this.genStatus === 'failed') {
            this.genError = res.data?.error_message || '生成失败'
            return 'failed'
          }
        } catch {
          // 状态拉失败不打断轮询，下一轮再试
        }
      }
      this.genError = '生成超时（>5 分钟），请稍后回到本页查看结果'
      return 'timeout'
    },

    async generate(month, llm = null) {
      this.generating = true
      this.genStatus = ''
      this.genError = ''
      try {
        const url = month ? `/api/reports/generate?month=${month}` : '/api/reports/generate'
        const res = await api.post(url, { llm })
        const data = res.data || {}
        const period = data.period || month

        // 后端返回 done 表示无数据 / 已即时完成；否则进入轮询
        if (data.status === 'done' && data.content) {
          this.current = data
          this.genStatus = 'done'
          await this.fetchList()
          return data
        }

        this.genStatus = data.status || 'pending'
        const final = await this._pollStatus(period)
        if (final === 'done') {
          await this.fetchOne(period)
          await this.fetchList()
          return this.current
        }
        if (final === 'failed') {
          throw new Error(this.genError || '生成失败')
        }
        // timeout：仍刷一次 list，让历史记录里能看到 pending/running 行
        await this.fetchList()
        throw new Error(this.genError)
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
