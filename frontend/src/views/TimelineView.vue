<template>
  <div class="timeline-view">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span>报告时间轴</span>
          <div>
            <el-select v-model="cycle" placeholder="全部周期" clearable style="width: 130px" @change="load">
              <el-option v-for="(label, value) in CYCLE_LABELS" :key="value" :label="label" :value="value" />
            </el-select>
            <el-button style="margin-left: 8px" :loading="loading" @click="load">刷新</el-button>
          </div>
        </div>
      </template>

      <div v-loading="loading">
        <el-empty v-if="!loading && items.length === 0" description="暂无报告，点击顶部周期卡片生成报告" />
        <div v-else class="timeline">
          <div v-for="it in items" :key="it.versionId" class="timeline-item" :style="{ '--node-color': cycleColor(it.cycle) }">
            <div class="tl-card">
              <div class="tl-head">
                <el-tag size="small" :color="cycleColor(it.cycle)" style="color: #fff; border: none">
                  {{ CYCLE_LABELS[it.cycle] || it.cycle }}
                </el-tag>
                <el-tag size="small" :type="statusType(it.status)">{{ VERSION_STATUS_LABELS[it.status] || it.status }}</el-tag>
                <span class="tl-time">{{ it.createdAt }}</span>
              </div>
              <div class="tl-title" @click="preview(it.versionId)">
                {{ it.title || `报告 v${it.versionNo}` }}
              </div>
              <div class="tl-window">
                {{ it.windowStart.slice(0, 10) }} ~ {{ it.windowEnd.slice(0, 10) }}
              </div>
              <div class="tl-metrics">
                <span class="m-item"><i class="dot" style="background: #409eff"></i>告警 <b>{{ it.alertTotal }}</b></span>
                <span class="m-item"><i class="dot" style="background: #f56c6c"></i>高危 <b>{{ it.alertHigh }}</b></span>
                <span class="m-item"><i class="dot" style="background: #e6a23c"></i>漏洞 <b>{{ it.vulnTotal }}</b></span>
                <span class="m-item"><i class="dot" style="background: #67c23a"></i>事件量 <b>{{ it.eventCount }}</b></span>
                <el-button class="tl-preview" size="small" link type="primary" @click="preview(it.versionId)">
                  预览报告
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Api } from '@/api'
import { notifyError } from '@/api/request'
import { CYCLE_LABELS, VERSION_STATUS_LABELS } from '@/types'
import type { TimelineItem } from '@/types'

const router = useRouter()
const loading = ref(false)
const cycle = ref('')
const items = ref<TimelineItem[]>([])

// 节点/标签颜色与 Dashboard 周期卡片一致
const CYCLE_COLORS: Record<string, string> = {
  DAILY: '#67c23a',
  WEEKLY: '#409eff',
  MONTHLY: '#e6a23c',
  QUARTERLY: '#f56c6c',
  YEARLY: '#909399',
}

function cycleColor(c: string) {
  return CYCLE_COLORS[c] || '#409eff'
}

function statusType(s: string) {
  return { DRAFT: 'warning', APPROVED: 'success', ARCHIVED: 'info', PUBLISHED: 'success', FAILED: 'danger', REVIEWING: 'primary' }[s] || 'info'
}

async function load() {
  loading.value = true
  const params: Record<string, string | number> = { limit: 50 }
  if (cycle.value) params.cycle = cycle.value
  const r = await Api.trend.timeline(params)
  notifyError(r)
  if (r.success) {
    items.value = (r.data as any)?.items || []
  }
  loading.value = false
}

function preview(versionId: number) {
  router.push(`/report-preview/${versionId}`)
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 竖向时间轴：节点圆点 + 连线 + 卡片 */
.timeline {
  position: relative;
  padding-left: 30px;
}
.timeline::before {
  content: '';
  position: absolute;
  left: 9px;
  top: 6px;
  bottom: 6px;
  width: 2px;
  background: #e4e7ed;
}
.timeline-item {
  position: relative;
  padding-bottom: 18px;
}
.timeline-item::before {
  content: '';
  position: absolute;
  left: -25px;
  top: 8px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--node-color);
  border: 2px solid #fff;
  box-shadow: 0 0 0 2px var(--node-color);
}
.tl-card {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 12px 16px;
  background: #fff;
  transition: box-shadow 0.2s;
}
.tl-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}
.tl-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.tl-time {
  margin-left: auto;
  color: #909399;
  font-size: 12px;
}
.tl-title {
  font-size: 15px;
  font-weight: 600;
  margin-top: 8px;
  cursor: pointer;
  color: #303133;
}
.tl-title:hover {
  color: #409eff;
}
.tl-window {
  color: #909399;
  font-size: 12px;
  margin-top: 4px;
}
.tl-metrics {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-top: 10px;
  flex-wrap: wrap;
}
.m-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  color: #606266;
}
.m-item b {
  font-size: 14px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.tl-preview {
  margin-left: auto;
}
</style>
