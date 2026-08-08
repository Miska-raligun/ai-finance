/**
 * Animal Island 风格的 ECharts 主题。
 *
 * 设计目标：与 :root CSS 变量保持一致——暖米底、棕褐文字、薄荷青强调、
 * 沙边网格线，让图表融入整体动森配色而不是默认冷灰。
 *
 * 用法：在 main.js 中 echarts.registerTheme('animal', config)；
 * 各 ECharts 组件 init 时传 theme='animal' 即可。
 */
export const ANIMAL_ECHARTS_THEME = {
  color: [
    '#19c8b9', '#f8a6b2', '#f7cd67', '#82d5bb', '#b77dee',
    '#889df0', '#e59266', '#8ac68a', '#fc736d', '#d1da49',
  ],
  backgroundColor: 'transparent',
  textStyle: {
    fontFamily: "'Nunito', 'Noto Sans SC', sans-serif",
    color: '#725d42',
  },
  title: {
    textStyle: { color: '#794f27', fontWeight: 700, fontFamily: "'Nunito', 'Noto Sans SC', sans-serif" },
    subtextStyle: { color: '#9f927d' },
  },
  legend: {
    textStyle: { color: '#725d42', fontFamily: "'Nunito', 'Noto Sans SC', sans-serif" },
    itemGap: 14,
  },
  tooltip: {
    backgroundColor: 'rgba(247, 243, 223, 0.98)',
    borderColor: '#c4b89e',
    borderWidth: 1.5,
    padding: [10, 14],
    textStyle: { color: '#725d42', fontWeight: 600, fontFamily: "'Nunito', 'Noto Sans SC', sans-serif" },
    extraCssText: 'border-radius: 14px; box-shadow: 0 4px 12px rgba(107,92,67,0.18);',
  },
  // 直角坐标轴
  categoryAxis: {
    axisLine: { lineStyle: { color: '#c4b89e' } },
    axisTick: { lineStyle: { color: '#c4b89e' } },
    axisLabel: { color: '#725d42', fontWeight: 600 },
    splitLine: { lineStyle: { color: '#e0d6bf', type: 'dashed' } },
    splitArea: { areaStyle: { color: ['transparent', 'rgba(247,243,223,0.4)'] } },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: '#9f927d', fontWeight: 600 },
    splitLine: { lineStyle: { color: '#e0d6bf', type: 'dashed' } },
    splitArea: { show: false },
  },
  // 系列默认 — 让线条柔和（适配儿童漫画风）
  line: {
    itemStyle: { borderWidth: 2 },
    lineStyle: { width: 3 },
    symbolSize: 7,
    symbol: 'circle',
    smooth: true,
  },
  bar: {
    itemStyle: {
      barBorderRadius: [8, 8, 0, 0],
      borderColor: 'rgba(0,0,0,0.06)',
    },
  },
  pie: {
    itemStyle: { borderWidth: 2, borderColor: 'rgba(247,243,223,0.85)' },
  },
  // 缩放手柄 / 工具栏配色
  dataZoom: {
    backgroundColor: 'rgba(247,243,223,0.3)',
    fillerColor: 'rgba(25,200,185,0.15)',
    borderColor: '#c4b89e',
    handleStyle: { color: '#19c8b9' },
    textStyle: { color: '#725d42' },
  },
  toolbox: {
    iconStyle: { borderColor: '#9f927d' },
    emphasis: { iconStyle: { borderColor: '#11a89b' } },
  },
}
