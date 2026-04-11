// src/stores/categories.js
import { defineStore } from 'pinia'
import api from '@/api'

/**
 * 分类缓存 + 账本刷新信号。
 *
 * - expense/income 分类列表按类型缓存，避免 RecordTable / BudgetAndCategoryPanel /
 *   CategoryManager 等组件各自重复请求 /api/categories。
 * - refreshCounter 替代原来的 `window.dispatchEvent('record_changed')` 事件广播，
 *   任何增删记录/分类/预算的操作调用 `bumpRefresh()` 即可触发所有监听者响应式更新。
 */
export const useCategoryStore = defineStore('categories', {
  state: () => ({
    expense: [],      // [{ id, name, type, user_id }]
    income: [],
    expenseLoaded: false,
    incomeLoaded: false,
    // 进行中请求去重（避免同一 Tab 并发渲染时多次请求）
    _pending: { expense: null, income: null },
    // 全局刷新信号：账本表格、图表、预算面板监听此值变化
    refreshCounter: 0,
  }),

  getters: {
    expenseNames: (state) => state.expense.map(c => c.name),
    incomeNames: (state) => state.income.map(c => c.name),
  },

  actions: {
    /**
     * 获取指定类型分类；若已有缓存且 force=false 则直接返回缓存。
     * @param {'expense'|'income'} type
     * @param {boolean} force 强制刷新
     */
    async fetchCategories(type, force = false) {
      const loadedKey = type === 'expense' ? 'expenseLoaded' : 'incomeLoaded'
      if (!force && this[loadedKey]) return this[type]
      if (this._pending[type]) return this._pending[type]

      const promise = api
        .get('/api/categories', { params: { type } })
        .then(res => {
          this[type] = res.data || []
          this[loadedKey] = true
          return this[type]
        })
        .finally(() => {
          this._pending[type] = null
        })

      this._pending[type] = promise
      return promise
    },

    /** 获取两种类型（RecordTable 同时需要时一次调用） */
    async fetchAll(force = false) {
      await Promise.all([
        this.fetchCategories('expense', force),
        this.fetchCategories('income', force),
      ])
    },

    /** 标记缓存失效；下次 fetchCategories 会重新请求后端 */
    invalidate(type) {
      if (!type || type === 'expense') {
        this.expenseLoaded = false
      }
      if (!type || type === 'income') {
        this.incomeLoaded = false
      }
    },

    /** 新增分类 */
    async addCategory(name, type) {
      await api.post('/api/categories', {
        name,
        type: type === 'income' ? '收入' : '支出',
      })
      this.invalidate(type)
      await this.fetchCategories(type, true)
      this.bumpRefresh()
    },

    /** 删除分类 */
    async deleteCategory(name, type) {
      await api.delete(`/api/categories/${encodeURIComponent(name)}`)
      this.invalidate(type)
      await this.fetchCategories(type, true)
      this.bumpRefresh()
    },

    /** 通知所有监听者（账本表格、图表、预算面板）重新拉取数据 */
    bumpRefresh() {
      this.refreshCounter++
    },
  },
})
