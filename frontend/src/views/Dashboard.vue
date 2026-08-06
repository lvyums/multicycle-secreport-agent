<template>
  <div class="dashboard">
    <el-row :gutter="16">
      <el-col :span="6" v-for="c in cycles" :key="c.value">
        <el-card shadow="hover" class="cycle-card" @click="onGenerate(c.value)">
          <div class="cycle-icon" :style="{ background: c.color }">
            <el-icon :size="26"><Calendar /></el-icon>
          </div>
          <div class="cycle-name">{{ c.label }}</div>
          <div class="cycle-desc">{{ c.desc }}</div>
          <div class="card-actions">
            <el-button type="primary" size="small" round>生成报告</el-button>
            <el-tooltip content="跳过幂等检查，强制新建任务重新生成" placement="top">
              <el-button size="small" round @click.stop="onGenerate(c.value, true)">↻ 重跑</el-button>
            </el-tooltip>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="mt16">
      <template #header>最近任务</template>
      <el-table :data="tasks" v-loading="loading" empty-text="暂无任务，点击上方周期卡片生成">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="周期" width="90">
          <template #default="{ row }">
            <el-tag size="small">{{ CYCLE_LABELS[row.cycle] || row.cycle }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="windowStart" label="统计窗口" min-width="200" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ TASK_STATUS_LABELS[row.status] || row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="triggerType" label="触发方式" width="100" />
        <el-table-column prop="createdAt" label="创建时间" width="170" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="goVersions(row.id)">版本</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Api } from '@/api'
import { notifyError } from '@/api/request'
import { CYCLE_LABELS, TASK_STATUS_LABELS } from '@/types'
import type { ReportTask } from '@/types'

const router = useRouter()
const loading = ref(false)
const tasks = ref<ReportTask[]>([])

const cycles = [
  { value: 'DAILY', label: '日报', desc: '昨日安全态势', color: '#67c23a' },
  { value: 'WEEKLY', label: '周报', desc: '上周态势汇总', color: '#409eff' },
  { value: 'MONTHLY', label: '月报', desc: '上月态势汇总', color: '#e6a23c' },
  { value: 'QUARTERLY', label: '季报', desc: '季度态势汇总', color: '#f56c6c' },
  { value: 'YEARLY', label: '年报', desc: '年度态势汇总', color: '#909399' },
]

function statusType(s: string) {
  return { SUCCESS: 'success', EMPTY: 'info', FAILED: 'danger', RUNNING: 'warning', PARTIAL: 'warning' }[s] || 'info'
}

async function loadTasks() {
  loading.value = true
  const r = await Api.report.list({ limit: 8 })
  notifyError(r)
  if (r.success) {
    tasks.value = (r.data as any)?.items || []
  }
  loading.value = false
}

async function onGenerate(cycle: string, rerun = false) {
  // V2.0 R：异步提交 → 轮询状态；rerun=true 强制重跑（跳过幂等复用）
  const r = await Api.report.generate(rerun ? { cycle, rerun: true } : { cycle })
  notifyError(r)
  if (!r.success || !r.data) return
  const data = (r.data as any) || {}
  const taskId = data.taskId ?? data.task_id
  if ((r.data as any)?.reused) {
    ElMessage.info(`窗口已有任务 #${taskId}（${(r.data as any)?.status}），直接复用`)
    loadTasks()
    return
  }
  ElMessage.success(`任务 #${taskId} 已提交，后台执行中…`)
  const begin = Date.now()
  for (let i = 0; i < 60; i++) {
    await new Promise((res) => setTimeout(res, 1000))
    const s = await Api.report.status(taskId)
    const st = (s.data as any)?.status
    if (st && !['PENDING', 'RUNNING'].includes(st)) {
      const cost = ((Date.now() - begin) / 1000).toFixed(1)
      const v = (s.data as any)?.versionId
      ElMessage[st === 'SUCCESS' ? 'success' : 'warning'](
        `任务 #${taskId} ${st}（${cost}s）${v ? `，版本 #${v}` : ''}`,
      )
      loadTasks()
      return
    }
  }
  ElMessage.warning('任务仍在执行，可稍后到任务日志查看')
  loadTasks()
}

function goVersions(taskId: number) {
  router.push({ path: '/reports', query: { taskId: String(taskId) } })
}

onMounted(loadTasks)
</script>

<style scoped>
.cycle-card {
  text-align: center;
  cursor: pointer;
}
.card-actions {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin-top: 4px;
}
.cycle-icon {
  width: 52px;
  height: 52px;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  margin-bottom: 10px;
}
.cycle-name {
  font-size: 17px;
  font-weight: 600;
}
.cycle-desc {
  color: #909399;
  font-size: 12px;
  margin: 6px 0 12px;
}
.mt16 {
  margin-top: 16px;
}
</style>
