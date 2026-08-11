<template>
  <div>
    <el-card>
      <template #header>
        <div class="toolbar">
          <span>调度配置</span>
          <el-switch v-model="enabled" active-text="启用调度" :disabled="!canManage" @change="onToggle" />
        </div>
      </template>

      <el-table :data="jobs" v-loading="loading">
        <el-table-column label="周期" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ CYCLE_LABELS[row.cycle] || row.cycle }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="cron" label="Cron 表达式" width="180" />
        <el-table-column prop="nextRun" label="下次触发" min-width="180" />
        <el-table-column label="说明" prop="desc" min-width="200" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="trigger(row.cycle)">立即触发</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 错过窗口检测 + 一键补跑（V2.8） -->
    <el-card class="mt16">
      <template #header>
        <div class="toolbar">
          <span>错过窗口检测</span>
          <div>
            <el-tag v-if="missedLoading" type="info" size="small" effect="plain">检测中…</el-tag>
            <el-tag v-else-if="missedItems.length" type="danger" size="small" effect="plain">
              发现 {{ missedItems.length }} 个错过窗口
            </el-tag>
            <el-tag v-else type="success" size="small" effect="plain">无错过窗口</el-tag>
            <el-button style="margin-left: 8px" size="small" @click="loadMissed">刷新检测</el-button>
          </div>
        </div>
      </template>

      <el-alert
        type="info" :closable="false" class="mb12"
        title="凌晨维护/断电/cron 错过时，本期报告缺失没人知道。系统按各周期往前检测 3 个已结束窗口，无任何生成记录的即列为错过，可一键补跑。"
      />

      <el-empty v-if="!missedLoading && missedItems.length === 0" description="最近窗口均有生成记录" :image-size="60" />

      <el-table v-else :data="missedItems" v-loading="missedLoading" stripe>
        <el-table-column label="周期" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ row.cycleLabel }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="windowStart" label="窗口开始" min-width="160" />
        <el-table-column prop="windowEnd" label="窗口结束" min-width="160" />
        <el-table-column prop="reason" label="原因" min-width="220" show-overflow-tooltip />
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" :loading="backfilling === row.windowStart" @click="backfill(row)">
              补跑
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Api } from '@/api'
import { notifyError } from '@/api/request'
import { CYCLE_LABELS } from '@/types'
import { isAdmin } from '@/utils/auth'

const canManage = isAdmin()

const loading = ref(false)
const enabled = ref(true)
const jobs = ref<any[]>([])

const missedLoading = ref(false)
const missedItems = ref<any[]>([])
const backfilling = ref('')

async function load() {
  loading.value = true
  const r = await Api.schedule.list()
  notifyError(r)
  if (r.success) {
    jobs.value = (r.data as any)?.jobs || []
    enabled.value = (r.data as any)?.enabled ?? true
  }
  loading.value = false
}

async function onToggle(val: boolean) {
  const r = await Api.schedule.toggle(val)
  notifyError(r)
  if (r.success) ElMessage.success(val ? '调度已启用' : '调度已停用')
}

async function trigger(cycle: string) {
  const r = await Api.schedule.trigger(cycle)
  notifyError(r)
  if (r.success) ElMessage.success(`已触发 ${CYCLE_LABELS[cycle] || cycle} 生成`)
}

// ── 错过窗口检测 + 补跑 ──
async function loadMissed() {
  missedLoading.value = true
  const r = await Api.schedule.missed()
  notifyError(r)
  if (r.success) {
    missedItems.value = (r.data as any)?.items || []
  }
  missedLoading.value = false
}

async function backfill(row: any) {
  await ElMessageBox.confirm(
    `确认补跑 ${row.cycleLabel} ${row.windowStart.slice(0, 10)}~${row.windowEnd.slice(0, 10)}？`,
    '一键补跑', { type: 'warning' },
  )
  backfilling.value = row.windowStart
  try {
    const r = await Api.schedule.backfill({
      cycle: row.cycle,
      windowStart: row.windowStart,
      windowEnd: row.windowEnd,
    })
    notifyError(r)
    if (r.success) {
      ElMessage.success(`已触发 ${row.cycleLabel} 补跑，生成后请到历史报告审核`)
      await loadMissed()
    }
  } finally {
    backfilling.value = ''
  }
}

onMounted(() => {
  load()
  loadMissed()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.mt16 {
  margin-top: 16px;
}
.mb12 {
  margin-bottom: 12px;
}
</style>
