<!-- components/ImportButton.vue — 导入 records/income(CSV/JSON,配套导出) -->
<template>
  <span class="import-btn-wrap">
    <el-button size="small" @click="showDialog = true">⬆ 导入</el-button>

    <el-dialog v-model="showDialog" title="导入数据" :width="dialogWidth">
      <div class="imp-body">
        <el-form label-width="64px" size="small">
          <el-form-item label="类型">
            <el-radio-group v-model="kind">
              <el-radio-button label="records">支出</el-radio-button>
              <el-radio-button label="income">收入</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="文件">
            <input ref="fileInput" type="file" accept=".csv,.json" @change="onPick" />
          </el-form-item>
        </el-form>
        <p class="imp-hint">
          支持导出的 CSV / JSON。表头需含 <b>日期 · 分类(或来源)· 金额 · 备注</b>。
          按「日期+金额+备注」自动去重,重复行跳过,不会覆盖已有数据。
        </p>
        <el-alert v-if="result" :type="result.imported ? 'success' : 'info'" :closable="false" class="imp-result">
          {{ result.message }}
        </el-alert>
      </div>
      <template #footer>
        <el-button @click="showDialog = false">关闭</el-button>
        <el-button type="primary" :loading="uploading" :disabled="!file" @click="doImport">导入</el-button>
      </template>
    </el-dialog>
  </span>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'
import bus from '@/event-bus'

const showDialog = ref(false)
const kind = ref('records')
const file = ref(null)
const fileInput = ref(null)
const uploading = ref(false)
const result = ref(null)
const dialogWidth = computed(() => window.innerWidth < 768 ? 'calc(100vw - 28px)' : '460px')

function onPick(e) {
  file.value = e.target.files[0] || null
  result.value = null
}

async function doImport() {
  if (!file.value) return
  uploading.value = true
  result.value = null
  try {
    const fd = new FormData()
    fd.append('type', kind.value)
    fd.append('file', file.value)
    const res = await api.post('/api/import', fd)
    result.value = res.data
    if (res.data.imported > 0) {
      ElMessage.success(res.data.message)
      // 通知账本/图表刷新
      bus.emit(kind.value === 'records' ? 'data:records' : 'data:income', { op: 'import' })
    } else {
      ElMessage.info(res.data.message)
    }
    if (fileInput.value) fileInput.value.value = ''
    file.value = null
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || '导入失败')
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped>
.import-btn-wrap { display: inline-flex; }
.imp-hint { font-size: 12px; color: var(--color-text-muted); line-height: 1.6; margin: 4px 0 0; }
.imp-result { margin-top: 10px; }
</style>
