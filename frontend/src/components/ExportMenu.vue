<template>
  <el-dropdown trigger="click" @command="onCommand">
    <el-button size="small">
      ⬇ 导出
      <el-icon style="margin-left: 4px"><ArrowDown /></el-icon>
    </el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="opt in items"
          :key="opt.command"
          :command="opt.command"
        >{{ opt.label }}</el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup>
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'

const props = defineProps({
  // ledger | investment | reports
  scope: { type: String, default: 'ledger' },
  // 报告导出需指定月份
  reportPeriod: { type: String, default: '' },
})

const items = computed(() => {
  if (props.scope === 'investment') {
    return [{ command: 'csv:assets', label: '📊 持仓 CSV' }]
  }
  if (props.scope === 'reports') {
    return [{ command: 'report:html', label: '🖨️ 当前月度报告（PDF）' }]
  }
  return [
    { command: 'csv:records', label: '💸 支出记录 CSV' },
    { command: 'csv:income',  label: '💰 收入记录 CSV' },
  ]
})

function onCommand(cmd) {
  if (cmd.startsWith('csv:')) {
    const kind = cmd.slice(4)
    window.open(`/api/export/csv?type=${encodeURIComponent(kind)}`, '_blank')
    return
  }
  if (cmd === 'report:html') {
    if (!props.reportPeriod) {
      ElMessage.warning('请先选择并加载一份月度报告')
      return
    }
    window.open(`/api/export/report.html?period=${encodeURIComponent(props.reportPeriod)}`, '_blank')
  }
}
</script>
