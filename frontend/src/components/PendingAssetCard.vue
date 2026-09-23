<template>
  <div
    v-show="rec._state !== 'cancelled'"
    :class="['pending-card', 'card-asset', rec._state === 'confirmed' ? 'card-confirmed' : '', rec._state === 'error' ? 'card-error' : '']"
  >
    <template v-if="rec._state === 'confirmed'">
      <div class="card-confirmed-header">
        <span class="amount-asset">📊 {{ rec._edit.name }}</span>
        <span class="card-category-text">{{ rec._edit.type }}</span>
        <span class="card-confirmed-badge">✓ 已入库</span>
      </div>
    </template>

    <template v-else>
      <div class="card-title">📊 待确认资产</div>
      <div class="card-fields">
        <div class="card-field">
          <label class="field-label">名称</label>
          <el-input v-model="rec._edit.name" size="small" placeholder="如：沪深300" />
        </div>
        <div class="card-field">
          <label class="field-label">类型</label>
          <el-select
            v-model="rec._edit.type"
            size="small" style="width:100%"
            placeholder="选择类型"
            :no-data-text="'暂无类型，请去投资页创建'"
          >
            <el-option v-for="t in assetTypes" :key="t.name" :value="t.name" :label="t.name" />
          </el-select>
        </div>
        <div v-if="schema.showSymbol" class="card-field">
          <label class="field-label">代码</label>
          <el-input v-model="rec._edit.symbol" size="small" :placeholder="symbolPlaceholder(rec._edit.type)" />
        </div>
        <div v-if="schema.showHoldings" class="card-field">
          <label class="field-label">持仓</label>
          <el-input-number v-model="rec._edit.holdings" :min="0" size="small" style="width:100%" controls-position="right" />
        </div>
        <div v-if="schema.showUnitCost" class="card-field">
          <label class="field-label">成本价（每股/每份）</label>
          <el-input-number
            v-model="rec._edit.cost_price"
            :min="0" :step="0.01" :precision="4"
            size="small" style="width:100%" controls-position="right"
          />
        </div>
        <div v-else-if="schema.hasCost" class="card-field">
          <label class="field-label">总成本</label>
          <el-input-number v-model="rec._edit.cost_basis" :min="0" size="small" style="width:100%" controls-position="right" />
        </div>
        <div v-if="!schema.autoQuote" class="card-field">
          <label class="field-label">{{ schema.hasCost ? '市值' : '当前余额' }}</label>
          <el-input-number v-model="rec._edit.current_value" :min="0" size="small" style="width:100%" controls-position="right" />
        </div>
        <div v-else class="card-field card-field-wide">
          <div class="auto-hint">
            总成本 = {{ Number(rec._edit.holdings) || 0 }} × ¥{{ Number(rec._edit.cost_price) || 0 }}
            = ¥{{ computedCost.toFixed(2) }}；当前市值由系统按代码自动拉取
          </div>
        </div>
      </div>
      <div v-if="rec._error" class="card-error-msg">⚠️ {{ rec._error }}</div>
      <div class="card-actions">
        <el-button size="small" plain @click="$emit('cancel')">取消</el-button>
        <el-button size="small" type="primary" :loading="rec._state === 'saving'" @click="$emit('confirm')">
          ✓ 确认入库
        </el-button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, watch, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useAssetTypesStore } from '@/stores/assetTypes'

const props = defineProps({
  rec: { type: Object, required: true },
})
defineEmits(['confirm', 'cancel'])

const typesStore = useAssetTypesStore()
const { types: assetTypes } = storeToRefs(typesStore)
onMounted(() => typesStore.fetchTypes())

const schema = computed(() => typesStore.schemaOf(props.rec._edit.type))
const isAutoType = (t) => typesStore.schemaOf(t).autoQuote

function symbolPlaceholder(type) {
  const t = typesStore.byName[type]
  if (!t) return '可选'
  if (t.quote_source === 'stock') return '如 sh600519 / 600519'
  if (t.quote_source === 'fund') return '如 510300（6位）'
  return '可选'
}

// 若 LLM 只给了总成本 + 持仓，反推出成本价作为初始值，保持证券类 UX 一致
watch(
  () => [props.rec._edit.type, props.rec._edit.holdings, props.rec._edit.cost_basis],
  ([type, holdings, basis]) => {
    if (!typesStore.schemaOf(type).showUnitCost) return
    if (props.rec._edit.cost_price != null && props.rec._edit.cost_price > 0) return
    const h = Number(holdings) || 0
    const b = Number(basis) || 0
    if (h > 0 && b > 0) {
      props.rec._edit.cost_price = Number((b / h).toFixed(4))
    }
  },
  { immediate: true },
)

const computedCost = computed(() => {
  const h = Number(props.rec._edit.holdings) || 0
  const cp = Number(props.rec._edit.cost_price) || 0
  return h * cp
})

// 证券类型：保持 cost_basis 与 持仓×成本价 同步，避免提交时漏算
watch(
  [() => props.rec._edit.type, () => props.rec._edit.holdings, () => props.rec._edit.cost_price],
  ([type]) => {
    if (!typesStore.schemaOf(type).showUnitCost) return
    props.rec._edit.cost_basis = Number(computedCost.value.toFixed(2))
  },
)
</script>

<style scoped>
.pending-card {
  background: var(--color-surface);
  border-radius: 12px;
  padding: 12px 14px;
  border: 1px solid var(--color-border);
  width: 100%;
  box-sizing: border-box;
  font-size: 13px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.05);
  border-left: 3px solid #6366f1;
}
.card-confirmed { background: var(--color-bg); opacity: 0.85; }
.card-error { border-left-color: #ef4444; }

.card-title {
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 8px;
  font-size: 13px;
}

.card-confirmed-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.amount-asset { color: #6366f1; font-weight: 700; font-size: 14px; }
.card-category-text { font-weight: 600; color: var(--color-text); flex: 1; }
.card-confirmed-badge { font-size: 11px; color: #22c55e; font-weight: 600; flex-shrink: 0; }

.card-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 12px;
  margin-bottom: 10px;
}
.card-field { display: flex; flex-direction: column; gap: 3px; }
.card-field-wide { grid-column: span 2; }
.field-label { font-size: 11px; color: var(--color-text-muted); font-weight: 500; }
.auto-hint {
  font-size: 11px; color: var(--color-primary);
  padding: 5px 8px; background: var(--color-primary-light); border-radius: 6px;
}

.card-error-msg {
  margin: 4px 0 8px;
  padding: 6px 10px;
  background: #FEF2F2;
  color: #B91C1C;
  border-radius: 6px;
  font-size: 12px;
}

.card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 768px) {
  .card-fields { grid-template-columns: 1fr; }
  .card-field-wide { grid-column: span 1; }
  .card-actions .el-button { flex: 1; }
}
</style>
