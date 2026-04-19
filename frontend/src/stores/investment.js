import { defineStore } from 'pinia'
import api from '@/api'

/**
 * 投资模块前端状态：资产 / 目标 / 组合 / 风险等级。
 */
export const useInvestmentStore = defineStore('investment', {
  state: () => ({
    assets: [],
    goals: [],
    portfolio: null,
    riskProfile: null,
    loading: false,
    refreshCounter: 0,
  }),

  getters: {
    totalValue: (state) => state.portfolio?.total_value || 0,
    riskLevel: (state) => state.riskProfile?.level || null,
  },

  actions: {
    bumpRefresh() {
      this.refreshCounter++
    },

    async refreshPrices() {
      const res = await api.post('/api/investment/refresh-prices')
      await this.fetchAssets()
      await this.fetchPortfolio()
      return res.data
    },

    async commitPendingAsset(payload) {
      const res = await api.post('/api/investment/commit-asset', payload)
      await this.fetchAssets()
      await this.fetchPortfolio()
      this.bumpRefresh()
      return res.data
    },

    async commitPendingGoal(payload) {
      const res = await api.post('/api/investment/commit-goal', payload)
      await this.fetchGoals()
      this.bumpRefresh()
      return res.data
    },

    async fetchAssets() {
      const res = await api.get('/api/investment/assets')
      this.assets = res.data || []
    },

    async createAsset(payload) {
      const res = await api.post('/api/investment/assets', payload)
      await this.fetchAssets()
      await this.fetchPortfolio()
      return res.data
    },

    async updateAsset(id, payload) {
      await api.patch(`/api/investment/assets/${id}`, payload)
      await this.fetchAssets()
      await this.fetchPortfolio()
    },

    async deleteAsset(id) {
      await api.delete(`/api/investment/assets/${id}`)
      await this.fetchAssets()
      await this.fetchPortfolio()
    },

    async fetchGoals() {
      const res = await api.get('/api/investment/goals')
      this.goals = res.data || []
    },

    async createGoal(payload) {
      await api.post('/api/investment/goals', payload)
      await this.fetchGoals()
    },

    async updateGoal(id, payload) {
      await api.patch(`/api/investment/goals/${id}`, payload)
      await this.fetchGoals()
    },

    async deleteGoal(id) {
      await api.delete(`/api/investment/goals/${id}`)
      await this.fetchGoals()
    },

    async fetchPortfolio() {
      const res = await api.get('/api/investment/portfolio')
      this.portfolio = res.data
    },

    async fetchRiskQuiz() {
      const res = await api.get('/api/investment/risk-quiz')
      this.riskProfile = res.data.profile
      return res.data
    },

    async submitRiskQuiz(answers, llm = null) {
      const res = await api.post('/api/investment/risk-quiz', { answers, llm })
      this.riskProfile = res.data
      return res.data
    },

    async askAdvisor({ mode = 'general', history = [], goal_id = null, monthly_net_cashflow = 0, llm = null } = {}) {
      const payload = { mode, history, llm }
      if (goal_id != null) payload.goal_id = goal_id
      if (monthly_net_cashflow) payload.monthly_net_cashflow = monthly_net_cashflow
      const res = await api.post('/api/investment/advisor/chat', payload)
      return res.data
    },
  },
})
