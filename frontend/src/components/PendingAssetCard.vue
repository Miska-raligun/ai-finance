<template>
  <div
    v-show="rec._state !== 'cancelled'"
    :class="['pending-card', 'card-asset', rec._state === 'confirmed' ? 'card-confirmed' : '', rec._state === 'error' ? 'card-error' : '']"
  >
    <template v-if="rec._state === 'confirmed'">
      <div class="card-confirmed-header">
        <span class="amount-asset">📊 {{ rec._edit.name }}</span>
        <span class="card-category-text">{{ TYPE_LABEL[rec._edit.type] || rec._edit.type }}</span>
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
          <el-select v-model="rec._edit.type" size="small" style="width:100%">
            <el-option v-for="(label, key) in TYPE_LABEL" :key="key" :value="key" :label="label" />
          </el-select>
        </div>
        <div class="card-field">
          <label class="field-label">代码</label>
          <el-input v-model="rec._edit.symbol" size="small" :placeholder="symbolPlaceholder(rec._edit.type)" />
        </div>
        <div class="card-field">
          <label class="field-label">持仓</label>
          <el-input-number v-model="rec._edit.holdings" :min="0" size="small" style="width:100%" controls-position="right" />
        </div>
        <div class="card-field">
          <label class="field-label">成本</label>
          <el-input-number v-model="rec._edit.cost_basis" :min="0" size="small" style="width:100%" controls-position="right" />
        </div>
        <div v-if="!isAutoType(rec._edit.type)" class="card-field">
          <label class="field-label">市值</label>
          <el-input-number v-model="rec._edit.current_value" :min="0" size="small" style="width:100%" controls-position="right" />
        </div>
        <div v-else class="card-field card-field-wide">
          <label class="field-label">当前市值</label>
          <div class="auto-hint">股票/基金：保存后按代码自动拉取最新价</div>
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
const TYPE_LABEL = {
  stock: '股票', fund: '基金', bond: '债券', cash: '现金',
  crypto: '加密货币', realestate: '房地产', other: '其他',
}

const AUTO_TYPES = new Set(['stock', 'fund'])
const isAutoType = (t) => AUTO_TYPES.has(t)

function symbolPlaceholder(type) {
  if (type === 'stock') return '如 sh600519 / 600519'
  if (type === 'fund') return '如 510300（6位）'
  return '可选'
}

defineProps({
  rec: { type: Object, required: true },
})
defineEmits(['confirm', 'cancel'])
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
  padding: 5px 8px; background: #F0F7FF; border-radius: 6px;
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
