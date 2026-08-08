<template>
  <el-dialog
    v-model="visible"
    title="🩺 财务体检"
    :width="dialogWidth"
    append-to-body
    @open="onOpen"
  >
    <div class="ck">
      <div class="ck-toolbar">
        <el-date-picker
          v-model="month"
          type="month"
          format="YYYY-MM"
          value-format="YYYY-MM"
          placeholder="选择月份"
          :clearable="false"
          @change="onMonthChange"
          style="width: 150px"
        />
        <el-button
          type="primary"
          :loading="store.computing"
          @click="run"
        >{{ store.computing ? '体检中…' : (result ? '重新体检' : '开始体检') }}</el-button>
      </div>

      <div v-if="store.loading" class="ck-loading">
        <el-skeleton :rows="5" animated />
      </div>

      <AiThinking
        v-if="store.computing"
        :steps="[
          '🐾 正在汇总你的真实财务数据',
          '🩺 Anon 在打健康分',
          '✍️ 整理四维体检报告…',
        ]"
        @cancel="cancel"
      />

      <template v-else-if="result && result.dimensions && result.dimensions.length">
        <div class="ck-gauge-row">
          <VChart theme="animal" :option="gaugeOption" class="ck-gauge" autoresize />
          <div class="ck-grade">
            <div class="ck-grade-name" :style="{ color: scoreColor }">{{ result.grade }}</div>
            <div class="ck-summary">{{ result.summary }}</div>
            <span v-if="result.source === 'fallback'" class="ck-tag">本地估算 · 配置 AI 更精准</span>
          </div>
        </div>

        <div class="ck-dims">
          <div v-for="(d, i) in result.dimensions" :key="i" class="ck-dim">
            <div class="ck-dim-head">
              <span class="ck-dim-name">{{ d.name }}</span>
              <strong class="ck-dim-score">{{ d.score }}<span class="ck-dim-max">/{{ d.max }}</span></strong>
            </div>
            <el-progress :percentage="pct(d)" :show-text="false" :stroke-width="8" :color="barColor(d)" />
            <div class="ck-dim-comment">{{ d.comment }}</div>
          </div>
        </div>

        <div v-if="result.report" class="ck-report" v-html="formattedReport"></div>

        <div v-if="store.history.length > 1" class="ck-trend">
          <div class="ck-trend-title">📈 健康分趋势</div>
          <VChart theme="animal" :option="trendOption" class="ck-trend-chart" autoresize />
        </div>

        <div class="ck-foot">数据来自你的真实记账与资产 · 仅供参考 🌿</div>
      </template>

      <EmptyHint
        v-else
        kind="island"
        title="还没有这个月的体检"
        hint="选个月份点「开始体检」，Anon 会根据你的储蓄率、预算、应急金和消费结构打个分。"
      />
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { use } from 'echarts/core'
import VChart from 'vue-echarts'
import { GaugeChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useCheckupStore } from '@/stores/checkup'
import { useUserStore } from '@/stores/user'
import EmptyHint from '@/components/EmptyHint.vue'
import AiThinking from '@/components/AiThinking.vue'

use([GaugeChart, LineChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue'])
const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const store = useCheckupStore()
const userStore = useUserStore()

const _mq = window.matchMedia('(max-width: 768px)')
const isMobile = ref(_mq.matches)
function _onMq(e) { isMobile.value = e.matches }
onMounted(() => _mq.addEventListener('change', _onMq))
onBeforeUnmount(() => _mq.removeEventListener('change', _onMq))
const dialogWidth = computed(() => isMobile.value ? 'calc(100vw - 28px)' : '560px')

function curMonth() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}
const month = ref(curMonth())
const result = computed(() => store.current)
const controller = ref(null)

async function onOpen() {
  await Promise.all([
    store.fetchCurrent(month.value).catch(() => {}),
    store.fetchHistory().catch(() => {}),
  ])
}

async function onMonthChange() {
  store.current = null
  await store.fetchCurrent(month.value).catch(() => {})
}

function cancel() {
  controller.value?.abort()
}

async function run() {
  controller.value = new AbortController()
  try {
    await store.compute(month.value, userStore.llmPayload, {
      signal: controller.value.signal,
    })
  } catch (e) {
    // 用户取消：静默
    if (e?.name === 'CanceledError' || e?.code === 'ERR_CANCELED') return
    ElMessage.error(e?.response?.data?.error || '体检失败，请稍后再试')
  } finally {
    controller.value = null
  }
}

const scoreColor = computed(() => {
  const s = result.value?.score ?? 0
  if (s >= 80) return '#15803D'
  if (s >= 60) return '#19c8b9'
  if (s >= 40) return '#f5c31c'
  return '#e05a5a'
})

function pct(d) {
  const max = Number(d.max) || 25
  return Math.round((Number(d.score) || 0) / max * 100)
}
function barColor(d) {
  const p = pct(d)
  if (p >= 80) return '#15803D'
  if (p >= 50) return '#19c8b9'
  if (p >= 30) return '#f5c31c'
  return '#e05a5a'
}

const formattedReport = computed(() => {
  const r = result.value?.report || ''
  const esc = r.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc.replace(/\n/g, '<br>')
})

const gaugeOption = computed(() => ({
  series: [{
    type: 'gauge',
    startAngle: 210,
    endAngle: -30,
    min: 0,
    max: 100,
    radius: '92%',
    center: ['50%', '58%'],
    progress: { show: false },
    axisLine: {
      lineStyle: {
        width: 14,
        color: [
          [0.4, '#e05a5a'],
          [0.6, '#f5c31c'],
          [0.8, '#19c8b9'],
          [1, '#6fba2c'],
        ],
      },
    },
    pointer: { width: 5, length: '60%', itemStyle: { color: 'auto' } },
    axisTick: { distance: -14, length: 5, lineStyle: { color: '#fff', width: 1 } },
    splitLine: { distance: -14, length: 14, lineStyle: { color: '#fff', width: 2 } },
    axisLabel: { distance: 16, color: '#9f927d', fontSize: 10 },
    anchor: { show: true, size: 12, itemStyle: { color: 'auto' } },
    detail: {
      valueAnimation: true,
      fontSize: 30,
      fontWeight: 900,
      offsetCenter: [0, '32%'],
      formatter: '{value}',
      color: scoreColor.value,
    },
    title: { offsetCenter: [0, '62%'], fontSize: 12, color: '#9f927d' },
    data: [{ value: result.value?.score ?? 0, name: '健康分' }],
  }],
}))

const trendOption = computed(() => ({
  grid: { top: 18, bottom: 24, left: 36, right: 12 },
  tooltip: { trigger: 'axis', formatter: p => `${p[0].axisValue}：${p[0].data} 分` },
  xAxis: { type: 'category', data: store.history.map(h => h.period.slice(2)) },
  yAxis: { type: 'value', min: 0, max: 100 },
  series: [{
    type: 'line',
    smooth: true,
    data: store.history.map(h => h.score),
    areaStyle: { opacity: 0.12 },
    lineStyle: { width: 3 },
  }],
}))
</script>

<style scoped>
.ck { display: flex; flex-direction: column; gap: 14px; }
.ck-toolbar { display: flex; gap: 10px; align-items: center; }
.ck-loading { padding: 8px 0; }

.ck-gauge-row { display: flex; align-items: center; gap: 8px; }
.ck-gauge { width: 200px; height: 160px; flex-shrink: 0; }
.ck-grade { min-width: 0; }
.ck-grade-name { font-size: 22px; font-weight: 900; }
.ck-summary { font-size: 13px; color: var(--color-text); line-height: 1.5; margin-top: 4px; }
.ck-tag {
  display: inline-block;
  margin-top: 8px;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 50px;
  background: var(--color-border);
  color: var(--color-text-muted);
}

.ck-dims { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 14px; }
.ck-dim { background: var(--color-surface-2); border-radius: 12px; padding: 10px 12px; }
.ck-dim-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
.ck-dim-name { font-size: 13px; font-weight: 700; color: var(--color-text-strong); }
.ck-dim-score { font-size: 14px; font-weight: 900; color: var(--color-text-strong); font-variant-numeric: tabular-nums; }
.ck-dim-max { font-size: 11px; color: var(--color-text-muted); font-weight: 600; }
.ck-dim-comment { font-size: 12px; color: var(--color-text-muted); line-height: 1.5; margin-top: 6px; }

.ck-report {
  font-size: 13px;
  line-height: 1.7;
  color: var(--color-text);
  background: var(--color-surface-2);
  border-radius: 12px;
  border-left: 3px solid var(--color-primary);
  padding: 12px 14px;
}

.ck-trend-title { font-size: 13px; font-weight: 700; color: var(--color-text-strong); margin-bottom: 4px; }
.ck-trend-chart { width: 100%; height: 160px; }

.ck-foot { font-size: 11px; color: var(--color-text-muted); text-align: center; }

@media (max-width: 768px) {
  .ck-gauge-row { flex-direction: column; text-align: center; }
  .ck-dims { grid-template-columns: 1fr; }
}
</style>
