<template>
  <div
    v-show="rec._state !== 'cancelled'"
    :class="['pending-card', 'card-goal', rec._state === 'confirmed' ? 'card-confirmed' : '', rec._state === 'error' ? 'card-error' : '']"
  >
    <template v-if="rec._state === 'confirmed'">
      <div class="card-confirmed-header">
        <span class="amount-goal">🎯 {{ rec._edit.name }}</span>
        <span class="card-category-text">¥{{ Number(rec._edit.target_amount).toFixed(0) }}</span>
        <span class="card-confirmed-badge">✓ 已入库</span>
      </div>
    </template>

    <template v-else>
      <div class="card-title">🎯 待确认理财目标</div>
      <div class="card-fields">
        <div class="card-field card-field-wide">
          <label class="field-label">名称</label>
          <el-input v-model="rec._edit.name" size="small" placeholder="如：买房首付" />
        </div>
        <div class="card-field">
          <label class="field-label">目标金额</label>
          <el-input-number v-model="rec._edit.target_amount" :min="0" :step="1000" size="small" style="width:100%" controls-position="right" />
        </div>
        <div class="card-field">
          <label class="field-label">已完成</label>
          <el-input-number v-model="rec._edit.current_progress" :min="0" :step="100" size="small" style="width:100%" controls-position="right" />
        </div>
        <div class="card-field">
          <label class="field-label">截止日期</label>
          <el-date-picker v-model="rec._edit.deadline" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%" />
        </div>
        <div class="card-field">
          <label class="field-label">优先级</label>
          <el-select v-model="rec._edit.priority" size="small" style="width:100%">
            <el-option :value="1" label="最高（红）" />
            <el-option :value="2" label="高（红）" />
            <el-option :value="3" label="中（橙）" />
            <el-option :value="4" label="低（灰）" />
            <el-option :value="5" label="最低（灰）" />
          </el-select>
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
  border-left: 3px solid #f59e0b;
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
.amount-goal { color: #f59e0b; font-weight: 700; font-size: 14px; }
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
