// src/stores/assetTypes.js
import { defineStore } from 'pinia'
import api from '@/api'

/**
 * 资产类型（用户自管理）缓存 + 表单所需的 shape 元数据。
 *
 * shape 决定表单字段是否出现，是前端唯一硬编码的 4 条记录；
 * 其它信息（label、quote_source）全部由用户在后端 asset_types 表里维护。
 */
export const SHAPE_SCHEMA = {
  security_auto:   { showSymbol: true,  showHoldings: true,  showUnitCost: true,  hasCost: true,  autoQuote: true  },
  security_manual: { showSymbol: true,  showHoldings: true,  showUnitCost: true,  hasCost: true,  autoQuote: false },
  lump:            { showSymbol: false, showHoldings: false, showUnitCost: false, hasCost: true,  autoQuote: false },
  cash:            { showSymbol: false, showHoldings: false, showUnitCost: false, hasCost: false, autoQuote: false },
}

export const SHAPE_LABEL = {
  security_auto:   '证券（自动行情）',
  security_manual: '证券（手填市值）',
  lump:            '一次性资产',
  cash:            '现金/余额',
}

const FALLBACK = { showSymbol: false, showHoldings: false, showUnitCost: false, hasCost: true, autoQuote: false }

export const useAssetTypesStore = defineStore('assetTypes', {
  state: () => ({
    types: [],              // [{ id, name, shape, quote_source }]
    loaded: false,
    _pending: null,
    refreshCounter: 0,
  }),

  getters: {
    names: (state) => state.types.map(t => t.name),
    byName: (state) => Object.fromEntries(state.types.map(t => [t.name, t])),
  },

  actions: {
    async fetchTypes(force = false) {
      if (!force && this.loaded) return this.types
      if (this._pending) return this._pending
      const promise = api.get('/api/investment/asset-types')
        .then(res => {
          this.types = res.data || []
          this.loaded = true
          return this.types
        })
        .finally(() => { this._pending = null })
      this._pending = promise
      return promise
    },

    invalidate() { this.loaded = false },

    async createType({ name, shape, quote_source = null }) {
      await api.post('/api/investment/asset-types', { name, shape, quote_source })
      this.invalidate()
      await this.fetchTypes(true)
      this.bumpRefresh()
    },

    async deleteType(name) {
      await api.delete(`/api/investment/asset-types/${encodeURIComponent(name)}`)
      this.invalidate()
      await this.fetchTypes(true)
      this.bumpRefresh()
    },

    /** 查指定类型的 shape 元数据；未知类型走 FALLBACK（lump 形态） */
    schemaOf(name) {
      const t = this.byName[name]
      if (!t) return FALLBACK
      return SHAPE_SCHEMA[t.shape] || FALLBACK
    },

    bumpRefresh() { this.refreshCounter++ },
  },
})
