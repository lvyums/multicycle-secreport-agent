<template>
  <div class="tasklogs-page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span>任务日志</span>
          <div class="right">
            <el-select v-model="status" placeholder="全部状态" clearable style="width: 130px" @change="load(1)">
              <el-option v-for="s in statusMeta" :key="s.value" :label="s.label" :value="s.value" />
            </el-select>
            <el-button size="small" @click="load(1)">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="items" v-loading="loading" stripe @expand-change="onExpand">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="detail-box" v-if="detail?.id === row.id">
              <el-descriptions :column="3" border size="small">
                <el-descriptions-item label="TraceID">{{ detail.traceId || '-' }}</el-descriptions-item>
                <el-descriptions-item label="开始时间">{{ detail.startedAt || '-' }}</el-descriptions-item>
                <el-descriptions-item label="结束时间">{{ detail.finishedAt || '-' }}</el-descriptions-item>
                <el-descriptions-item label="触发来源">{{ triggerLabel(detail.triggerType) }}</el-descriptions-item>
                <el-descriptions-item label="耗时">{{ detail.durationMs }} ms</el-descriptions-item>
                <el-descriptions-item label="关联版本">
                  <el-button v-if="detail.versionId" link type="primary" size="small"
                    @click="goPreview(detail.versionId)">版本 #{{ detail.versionId }}</el-button>
                  <span v-else>-</span>
                </el-descriptions-item>
              </el-descriptions>
              <div v-if="detail.errorMsg" class="error-box">错误: {{ detail.errorMsg }}</div>
              <div class="stats-title">数据源统计</div>
              <el-table :data="statsRows" size="small" border>
                <el-table-column prop="source" label="数据源" />
                <el-table-column prop="ok" label="状态" width="80">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.ok ? 'success' : 'danger'">{{ row.ok ? 'OK' : 'FAIL' }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="count" label="拉取数" width="90" />
                <el-table-column prop="error" label="错误信息" min-width="160" show-overflow-tooltip />
              </el-table>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="cycleLabel" label="周期" width="80" />
        <el-table-column label="窗口" min-width="230">
          <template #default="{ row }">{{ row.windowStart }} ~ {{ row.windowEnd }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ row.statusLabel }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="durationMs" label="耗时(ms)" width="100" />
        <el-table-column label="触发" width="90">
          <template #default="{ row }">{{ triggerLabel(row.triggerType) }}</template>
        </el-table-column>
        <el-table-column prop="createdAt" label="创建时间" width="170" />
      </el-table>

      <el-pagination v-if="total > limit" layout="prev, pager, next" :total="total"
        :page-size="limit" :current-page="page" @current-change="load" class="pager" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Api } from '@/api'

const router = useRouter()
const loading = ref(false)
const items = ref<any[]>([])
const detail = ref<any>(null)
const status = ref('')
const page = ref(1)
const limit = 15
const total = ref(0)

const statusMeta = [
  { value: 'PENDING', label: '待执行' },
  { value: 'RUNNING', label: '执行中' },
  { value: 'SUCCESS', label: '成功' },
  { value: 'EMPTY', label: '空数据' },
  { value: 'PARTIAL', label: '部分成功' },
  { value: 'FAILED', label: '失败' },
]
const statusType = (s: string) =>
  ({ SUCCESS: 'success', EMPTY: 'info', PARTIAL: 'warning', FAILED: 'danger' }[s] || 'info')
const triggerLabel = (t: string) =>
  ({ MANUAL: '手动', SCHEDULE: '调度', RERUN: '重跑' }[t] || t || '-')

const statsRows = computed(() => {
  const s = detail.value?.dataSourceStats || {}
  return Object.entries(s).map(([source, v]: [string, any]) => ({
    source,
    ok: v?.ok !== false,
    count: v?.count || 0,
    error: v?.error || '',
  }))
})

async function load(p?: number) {
  if (p) page.value = p
  loading.value = true
  try {
    const params: Record<string, string | number> = { page: page.value, limit }
    if (status.value) params.status = status.value
    const r = await Api.report.list(params)
    items.value = r.data.items
    total.value = r.data.total
  } finally {
    loading.value = false
  }
}

async function onExpand(row: any, expanded: any[]) {
  if (expanded.includes(row)) {
    const r = await Api.report.detail(row.id)
    detail.value = r.data
  }
}

const goPreview = (versionId: number) => router.push(`/report-preview/${versionId}`)

onMounted(() => load(1))
</script>

<style scoped>
.detail-box {
  padding: 12px 16px;
  background: #fafafa;
}
.error-box {
  margin-top: 8px;
  padding: 8px 12px;
  background: #fef0f0;
  color: #f56c6c;
  border-radius: 4px;
  font-size: 13px;
}
.stats-title {
  margin: 12px 0 6px;
  font-weight: 600;
  font-size: 13px;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>
