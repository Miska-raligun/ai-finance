<template>
  <div class="asset-type-manager">
    <div class="form-grid">
      <el-input
        v-model="form.name"
        size="small"
        placeholder="如 A股 / 美债 / 活期存款"
        class="name-input"
        @keyup.enter="addType"
      />
      <el-select v-model="form.shape" size="small" class="shape-select">
        <el-option
          v-for="(label, key) in SHAPE_LABEL"
          :key="key" :value="key" :label="label"
        />
      </el-select>
      <el-select
        v-if="form.shape === 'security_auto'"
        v-model="form.quote_source"
        size="small"
        placeholder="行情源"
        class="quote-select"
      >
        <el-option value="stock" label="A 股（新浪）" />
        <el-option value="fund" label="公募基金（天天基金）" />
      </el-select>
      <el-button type="primary" size="small" @click="addType">添加</el-button>
    </div>

    <div class="shape-hint">{{ shapeHint }}</div>

    <div class="tags-wrap">
      <el-tag
        v-for="t in types"
        :key="t.name"
        closable
        size="default"
        class="type-tag"
        @close="onDelete(t)"
      >
        <span class="type-name">{{ t.name }}</span>
        <span class="type-shape">{{ SHAPE_LABEL[t.shape] }}{{ t.quote_source ? ' · ' + t.quote_source : '' }}</span>
      </el-tag>
      <span v-if="!types.length" class="empty-tip">暂无类型，先添加一个再去新增资产</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { storeToRefs } from 'pinia'
import { useAssetTypesStore, SHAPE_LABEL } from '@/stores/assetTypes'

const store = useAssetTypesStore()
const { types } = storeToRefs(store)

const form = reactive({
  name: '',
  shape: 'lump',
  quote_source: 'stock',
})

const shapeHint = computed(() => {
  if (form.shape === 'security_auto') return '证券类：填代码+持仓+成本价，系统按行情源自动同步市值'
  if (form.shape === 'security_manual') return '证券类：填代码+持仓+成本价，市值需手填（无自动行情源）'
  if (form.shape === 'cash') return '现金类：只填当前余额，无成本/盈亏概念'
  return '一次性资产：填总成本和当前市值（适合债券、房产、其它）'
})

async function addType() {
  if (!form.name.trim()) { ElMessage.warning('请填类型名称'); return }
  if (form.shape === 'security_auto' && !form.quote_source) {
    ElMessage.warning('证券（自动行情）需选行情源')
    return
  }
  try {
    await store.createType({
      name: form.name.trim(),
      shape: form.shape,
      quote_source: form.shape === 'security_auto' ? form.quote_source : null,
    })
    form.name = ''
    ElMessage.success('已添加')
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || '添加失败')
  }
}

async function onDelete(t) {
  try {
    await ElMessageBox.confirm(
      `确定删除类型「${t.name}」？`,
      '确认删除',
      { type: 'warning' },
    )
    await store.deleteType(t.name)
    ElMessage.success('已删除')
  } catch (e) {
    if (e === 'cancel') return
    ElMessage.error(e?.response?.data?.error || '删除失败，可能仍有资产在引用此类型')
  }
}

onMounted(() => store.fetchTypes())
</script>

<style scoped>
.asset-type-manager { padding: 4px 0; }
.form-grid {
  display: flex; gap: 8px; align-items: center;
  flex-wrap: wrap; margin-bottom: 8px;
}
.name-input { flex: 1; min-width: 160px; }
.shape-select { width: 180px; }
.quote-select { width: 180px; }
.shape-hint {
  font-size: 12px; color: var(--color-text-muted);
  margin: 4px 0 12px;
}
.tags-wrap {
  display: flex; flex-wrap: wrap; gap: 8px; min-height: 32px;
}
.type-tag {
  background: var(--color-primary-light) !important;
  color: var(--color-primary) !important;
  border-color: rgba(79,70,229,0.2) !important;
  border-radius: 6px !important;
  display: inline-flex; gap: 6px; align-items: center;
}
.type-tag .type-shape {
  font-size: 11px; font-weight: 400;
  color: var(--color-text-muted);
}
.empty-tip { font-size: 13px; color: var(--color-text-muted); }

@media (max-width: 768px) {
  .form-grid { flex-direction: column; align-items: stretch; }
  .name-input, .shape-select, .quote-select { width: 100%; }
}
</style>
