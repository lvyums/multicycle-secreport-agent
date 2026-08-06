<template>
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
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Api } from '@/api'
import { notifyError } from '@/api/request'
import { CYCLE_LABELS } from '@/types'
import { isAdmin } from '@/utils/auth'

const canManage = isAdmin()

const loading = ref(false)
const enabled = ref(true)
const jobs = ref<any[]>([])

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

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
