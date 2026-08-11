<template>
  <div class="trend-view">
    <!-- 工具条 -->
    <el-card class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <el-radio-group v-model="cycle" @change="load">
            <el-radio-button v-for="(label, value) in CYCLE_LABELS" :key="value" :value="value">
              {{ label }}
            </el-radio-button>
          </el-radio-group>
          <el-switch
            v-model="includeEmpty"
            class="ml12"
            active-text="含空窗口"
            inactive-text="过滤空窗口"
            @change="load"
          />
        </div>
        <el-button :loading="loading" @click="load">刷新</el-button>
      </div>
    </el-card>

    <!-- 环比摘要 -->
    <el-row :gutter="16" class="mt16">
      <el-col :span="6" v-for="k in summaryCards" :key="k.key">
        <el-card shadow="hover" class="summary-card">
          <div class="summary-label">{{ k.label }}</div>
          <div class="summary-value" :style="{ color: k.color }">
            {{ k.value }}
            <span class="summary-delta" :class="deltaClass(k.delta)">
              {{ k.deltaText }}
            </span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 主图：告警 / 漏洞趋势 -->
    <el-card class="mt16">
      <template #header>
        <span>{{ cycleLabel }} · 告警与漏洞趋势</span>
        <span class="card-sub">（同窗口重跑取最新，空窗口默认过滤）</span>
      </template>
      <TrendChart v-if="points.length" :points="points" height="360px" />
      <el-empty v-else description="暂无趋势数据，请先生成报告或运行种子脚本" />
    </el-card>

    <!-- 副图：事件量 + 关闭率 -->
    <el-card class="mt16">
      <template #header>事件量与关闭率</template>
      <TrendChart
        v-if="points.length"
        :points="points"
        :series="eventSeries"
        height="280px"
        y-axis-name="事件量"
      />
      <el-empty v-else description="暂无数据" />
    </el-card>

    <!-- 明细表 -->
    <el-card class="mt16">
      <template #header>各期指标明细</template>
      <el-table :data="points" v-loading="loading" empty-text="暂无数据" size="small">
        <el-table-column prop="label" label="窗口" min-width="110" fixed />
        <el-table-column label="告警总数" width="90">
          <template #default="{ row }"><b>{{ row.alertTotal }}</b></template>
        </el-table-column>
        <el-table-column label="高危" width="70">
          <template #default="{ row }">
            <el-tag size="small" type="danger">{{ row.alertHigh }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="中危" width="70">
          <template #default="{ row }">
            <el-tag size="small" type="warning">{{ row.alertMedium }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="低危" width="70">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ row.alertLow }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="关闭率" width="90">
          <template #default="{ row }">{{ (row.alertCloseRate * 100).toFixed(1) }}%</template>
        </el-table-column>
        <el-table-column label="漏洞总数" width="90">
          <template #default="{ row }"><b>{{ row.vulnTotal }}</b></template>
        </el-table-column>
        <el-table-column label="未修复" width="80">
          <template #default="{ row }">{{ row.vulnUnfixed }}</template>
        </el-table-column>
        <el-table-column label="未修复高危" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.vulnUnfixedHigh > 0" size="small" type="danger">{{ row.vulnUnfixedHigh }}</el-tag>
            <span v-else>0</span>
          </template>
        </el-table-column>
        <el-table-column label="事件量" width="80">
          <template #default="{ row }">{{ row.eventCount }}</template>
        </el-table-column>
        <el-table-column prop="windowStart" label="窗口开始" min-width="150" />
        <el-table-column prop="createdAt" label="生成时间" width="170" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Api } from '@/api'
import { notifyError } from '@/api/request'
import { CYCLE_LABELS } from '@/types'
import type { TrendPoint, TrendSeries } from '@/types'
import TrendChart from '@/components/TrendChart.vue'
import type { TrendSeriesDef } from '@/components/TrendChart.vue'

const loading = ref(false)
const cycle = ref('MONTHLY')
const includeEmpty = ref(false)
const series = ref<TrendSeries | null>(null)

const points = computed<TrendPoint[]>(() => series.value?.points || [])
const cycleLabel = computed(() => CYCLE_LABELS[cycle.value] || cycle.value)

// 副图：事件量柱状 + 两条关闭率百分比线
const eventSeries: TrendSeriesDef[] = [
  { key: 'eventCount', name: '事件量', color: '#67c23a', type: 'bar' },
  { key: 'alertCloseRate', name: '告警关闭率', color: '#409eff', percent: true },
  { key: 'vulnCloseRate', name: '漏洞关闭率', color: '#e6a23c', percent: true },
]

// 环比摘要：最近一期 vs 上一期
const summaryCards = computed(() => {
  const pts = points.value
  if (pts.length === 0) {
    return [
      { key: 'alertTotal', label: '告警总数', value: '-', delta: 0, deltaText: '', color: '#409eff' },
      { key: 'alertHigh', label: '高危告警', value: '-', delta: 0, deltaText: '', color: '#f56c6c' },
      { key: 'vulnTotal', label: '漏洞总数', value: '-', delta: 0, deltaText: '', color: '#e6a23c' },
      { key: 'eventCount', label: '事件量', value: '-', delta: 0, deltaText: '', color: '#67c23a' },
    ]
  }
  const cur = pts[pts.length - 1]
  const prev = pts.length > 1 ? pts[pts.length - 2] : null
  const card = (key: keyof TrendPoint, label: string, color: string) => {
    const v = Number(cur[key]) || 0
    const p = prev ? Number(prev[key]) || 0 : null
    const delta = p !== null && p > 0 ? ((v - p) / p) * 100 : null
    const deltaText =
      delta === null ? '' : `${delta >= 0 ? '↑' : '↓'}${Math.abs(delta).toFixed(1)}% 环比`
    return { key, label, value: v, delta: delta ?? 0, deltaText, color }
  }
  return [
    card('alertTotal', '告警总数', '#409eff'),
    card('alertHigh', '高危告警', '#f56c6c'),
    card('vulnTotal', '漏洞总数', '#e6a23c'),
    card('eventCount', '事件量', '#67c23a'),
  ]
})

function deltaClass(delta: number) {
  if (delta === 0) return ''
  // 告警/漏洞类指标：下降是好（绿色），上升是坏（红色）
  return delta > 0 ? 'delta-up' : 'delta-down'
}

async function load() {
  loading.value = true
  const r = await Api.trend.series({
    cycle: cycle.value,
    limit: 12,
    include_empty: includeEmpty.value ? 1 : 0,
  })
  notifyError(r)
  if (r.success) {
    series.value = r.data as TrendSeries
  }
  loading.value = false
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.toolbar-left {
  display: flex;
  align-items: center;
}
.ml12 {
  margin-left: 12px;
}
.mt16 {
  margin-top: 16px;
}
.card-sub {
  color: #909399;
  font-size: 12px;
  margin-left: 8px;
  font-weight: normal;
}
.summary-card {
  text-align: center;
}
.summary-label {
  color: #909399;
  font-size: 13px;
}
.summary-value {
  font-size: 26px;
  font-weight: 700;
  margin-top: 6px;
}
.summary-delta {
  font-size: 12px;
  font-weight: normal;
  margin-left: 6px;
}
.delta-up {
  color: #f56c6c;
}
.delta-down {
  color: #67c23a;
}
</style>
