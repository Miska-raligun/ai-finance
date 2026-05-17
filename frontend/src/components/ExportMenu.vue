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
          :divided="opt.divided"
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
    return [
      { command: 'csv:assets',  label: '📊 持仓 CSV' },
      { command: 'xlsx:assets', label: '📗 持仓 Excel' },
      { command: 'json:assets', label: '🧾 持仓 JSON' },
    ]
  }
  if (props.scope === 'reports') {
    return [{ command: 'report:html', label: '🖨️ 当前月度报告（PDF）' }]
  }
  return [
    { command: 'csv:records',  label: '💸 支出 CSV' },
    { command: 'xlsx:records', label: '📗 支出 Excel' },
    { command: 'json:records', label: '🧾 支出 JSON' },
    { divided: true, command: 'csv:income',  label: '💰 收入 CSV' },
    { command: 'xlsx:income', label: '📗 收入 Excel' },
    { command: 'json:income', label: '🧾 收入 JSON' },
  ]
})

function onCommand(cmd) {
  // 格式:类型 — csv:records / xlsx:assets / json:income
  if (cmd === 'report:html') {
    if (!props.reportPeriod) {
      ElMessage.warning('请先选择并加载一份月度报告')
      return
    }
    window.open(`/api/export/report.html?period=${encodeURIComponent(props.reportPeriod)}`, '_blank')
    return
  }
  const [fmt, kind] = cmd.split(':')
  if (!fmt || !kind) return
  window.open(
    `/api/export?type=${encodeURIComponent(kind)}&format=${encodeURIComponent(fmt)}`,
    '_blank',
  )
}
</script>
