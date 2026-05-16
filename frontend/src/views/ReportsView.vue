<template>
  <div class="reports-page">
    <div class="page-header">
      <h2 class="page-title">📑 月度报告</h2>
      <div class="header-actions">
        <el-date-picker
          v-model="month"
          type="month"
          format="YYYY-MM"
          value-format="YYYY-MM"
          placeholder="选择月份"
          style="width: 160px"
        />
        <el-button
          type="primary"
          :loading="store.generating"
          :disabled="!month"
          @click="onGenerate"
        >
          ✨ 生成本月报告
        </el-button>
        <ExportMenu scope="reports" :report-period="store.current?.period || ''" />
      </div>
    </div>

    <div class="reports-layout">
      <el-card class="side-list animal-pop" :style="{ '--i': 0 }">
        <template #header>历史报告</template>
        <EmptyHint
          v-if="!store.list.length"
          kind="letter"
          title="还没有月度报告"
          hint="选个月份点「✨ 生成本月报告」试试，Anon 会帮你写一份带建议的总结。"
        />
        <div
          v-for="r in store.list"
          :key="r.period"
          class="period-row"
          :class="{ active: store.current?.period === r.period }"
          @click="select(r.period)"
        >
          <div class="period-name">{{ r.period }}</div>
          <div class="period-time">{{ formatTime(r.created_at) }}</div>
          <el-button
            link
            type="danger"
            size="small"
            @click.stop="remove(r.period)"
          >删除</el-button>
        </div>
      </el-card>

      <div class="main-pane animal-pop" :style="{ '--i': 1 }">
        <el-skeleton v-if="store.loading" :rows="6" animated />
        <MonthlyReport v-else :report="store.current" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onActivated, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useReportsStore } from '@/stores/reports'
import { useUserStore } from '@/stores/user'
import MonthlyReport from '@/components/MonthlyReport.vue'
import ExportMenu from '@/components/ExportMenu.vue'
import EmptyHint from '@/components/EmptyHint.vue'

const store = useReportsStore()
const userStore = useUserStore()
const month = ref(currentMonth())

function currentMonth() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

function formatTime(iso) {
  if (!iso) return ''
  return iso.replace('T', ' ').slice(0, 16)
}

async function onGenerate() {
  try {
    ElMessage.info('生成中…LLM 写整月报告通常需要 1-3 分钟，可继续浏览其他页面')
    const data = await store.generate(month.value, userStore.llmPayload)
    if (data?.content?.includes('无任何记录')) {
      ElMessage.warning('该月暂无记账数据')
    } else {
      ElMessage.success(`已生成 ${data?.period || month.value} 月度报告`)
    }
  } catch (e) {
    ElMessage.error(e.message || e.response?.data?.error || '生成失败，请稍后重试')
  }
}

async function select(period) {
  try {
    await store.fetchOne(period)
  } catch (e) {
    ElMessage.error('加载报告失败')
  }
}

async function remove(period) {
  try {
    await ElMessageBox.confirm(`确定删除 ${period} 月度报告？`, '提示', {
      type: 'warning',
    })
    await store.remove(period)
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}

onMounted(async () => {
  await store.fetchList()
  if (store.list.length) {
    await select(store.list[0].period)
  }
})

// keep-alive 下切回本页时刷新列表，避免在别处生成 / 删除报告后回来看到陈旧
// 数据。10 秒节流，避免来回切页造成无谓请求。
let _lastFetchAt = 0
onActivated(() => {
  const now = Date.now()
  if (now - _lastFetchAt < 10_000) return
  _lastFetchAt = now
  store.fetchList()
})
</script>

<style scoped>
.reports-page {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  box-sizing: border-box;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.page-title { margin: 0; font-size: 20px; font-weight: 600; }
.header-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.reports-layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 16px;
  flex: 1;
  min-height: 0;
}
.side-list {
  height: fit-content;
  max-height: calc(100vh - 160px);
  overflow-y: auto;
}
.empty {
  text-align: center;
  color: var(--color-text-muted, var(--color-text-muted));
  padding: 18px 0;
  font-size: 13px;
}
.period-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 8px;
  align-items: center;
  padding: 8px 6px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}
.period-row:hover { background: var(--color-surface-2); }
.period-row.active {
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.3);
}
.period-name { font-weight: 600; font-size: 14px; }
.period-time { font-size: 12px; color: var(--color-text-muted, var(--color-text-muted)); }
.main-pane { min-width: 0; }

@media (max-width: 768px) {
  .reports-layout { grid-template-columns: 1fr; }
}
</style>
