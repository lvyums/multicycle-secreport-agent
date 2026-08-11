<template>
  <div ref="chartRef" class="trend-chart" :style="{ height }"></div>
</template>

<script lang="ts">
/** 模块作用域常量：withDefaults 默认值不可引用 <script setup> 局部变量（会被 hoist） */
import type { TrendPoint } from '@/types'

export interface TrendSeriesDef {
  key: keyof TrendPoint
  name: string
  color: string
  type?: 'line' | 'bar'
  /** 百分比系列走右侧 y 轴（如关闭率） */
  percent?: boolean
}

export const DEFAULT_SERIES: TrendSeriesDef[] = [
  { key: 'alertTotal', name: '告警总数', color: '#409eff' },
  { key: 'alertHigh', name: '高危告警', color: '#f56c6c' },
  { key: 'vulnTotal', name: '漏洞总数', color: '#e6a23c' },
  { key: 'vulnUnfixedHigh', name: '未修复高危', color: '#c45656' },
]
</script>

<script setup lang="ts">
/** TrendChart — echarts 封装（V2.6）
 * 默认四条主线：告警总数 / 高危告警 / 漏洞总数 / 未修复高危
 * 可传自定义 series（如事件量柱状 + 关闭率百分比双轴）
 * tooltip 附带关闭率、事件数；自动随容器 resize
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = withDefaults(
  defineProps<{
    points: TrendPoint[]
    series?: TrendSeriesDef[]
    height?: string
    yAxisName?: string
    yAxis2Name?: string
  }>(),
  { height: '340px', series: () => DEFAULT_SERIES, yAxisName: '数量', yAxis2Name: '百分比' },
)

const chartRef = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let observer: ResizeObserver | null = null

function buildOption(points: TrendPoint[], series: TrendSeriesDef[]): echarts.EChartsOption {
  const labels = points.map((p) => p.label)
  const hasPercent = series.some((s) => s.percent)
  return {
    tooltip: {
      trigger: 'axis',
      confine: true,
      formatter(params: any) {
        const idx = params?.[0]?.dataIndex ?? 0
        const p = points[idx]
        if (!p) return ''
        const rows = params
          .map((s: any) => `${s.marker}${s.seriesName}：<b>${s.value}${s.axisValueLabel?.includes('%') ? '%' : ''}</b>`)
          .join('<br/>')
        const extra = [
          `事件量：<b>${p.eventCount}</b>`,
          `告警关闭率：<b>${(p.alertCloseRate * 100).toFixed(1)}%</b>`,
          `漏洞关闭率：<b>${(p.vulnCloseRate * 100).toFixed(1)}%</b>`,
        ].join('<br/>')
        return `<b>${p.label}</b>（${p.windowStart.slice(0, 10)} ~ ${p.windowEnd.slice(0, 10)}）<br/>${rows}<br/>${extra}`
      },
    },
    legend: { top: 0, data: series.map((s) => s.name) },
    grid: { left: 50, right: hasPercent ? 56 : 24, top: 36, bottom: 28 },
    xAxis: {
      type: 'category',
      data: labels,
      boundaryGap: series.some((s) => s.type === 'bar'),
      axisLabel: { interval: 0, rotate: labels.length > 8 ? 30 : 0, fontSize: 11 },
    },
    yAxis: hasPercent
      ? [
          { type: 'value', minInterval: 1, name: props.yAxisName },
          { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' }, name: props.yAxis2Name, splitLine: { show: false } },
        ]
      : { type: 'value', minInterval: 1, name: props.yAxisName },
    series: series.map((s) => ({
      name: s.name,
      type: s.type || 'line',
      smooth: s.type !== 'bar',
      barMaxWidth: 22,
      symbolSize: 6,
      yAxisIndex: s.percent ? 1 : 0,
      data: points.map((p) => (s.percent ? Number((Number(p[s.key]) || 0) * 100).toFixed(1) : Number(p[s.key]) || 0)),
      itemStyle: { color: s.color },
      lineStyle: { width: 2, color: s.color },
      emphasis: { focus: 'series' },
    })),
  }
}

function render() {
  if (!chart || !props.points.length) return
  chart.setOption(buildOption(props.points, props.series), true)
}

watch(
  () => props.points,
  () => render(),
  { deep: true },
)
watch(
  () => props.series,
  () => render(),
  { deep: true },
)

onMounted(() => {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value)
  render()
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(chartRef.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.trend-chart {
  width: 100%;
}
</style>
