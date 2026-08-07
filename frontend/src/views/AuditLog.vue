<template>
  <div class="audit-page">
    <el-card shadow="never">
      <template #header>
        <div class="page-header">
          <span>审计日志（操作留痕：登录/改密/导出/状态变更）</span>
          <div class="header-actions">
            <el-select v-model="actionFilter" placeholder="动作筛选" clearable style="width: 180px" @change="load">
              <el-option v-for="a in actions" :key="a" :label="a" :value="a" />
            </el-select>
            <el-button type="primary" :loading="loading" @click="load">刷新</el-button>
          </div>
        </div>
      </template>
      <el-table :data="items" v-loading="loading" stripe size="small" max-height="600">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="createdAt" label="时间" width="170" />
        <el-table-column prop="operator" label="操作者" width="120" />
        <el-table-column prop="action" label="动作" width="150">
          <template #default="{ row }">
            <el-tag size="small" :type="tagType(row.action)">{{ row.action }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="targetType" label="目标类型" width="130" />
        <el-table-column prop="targetId" label="目标ID" width="80" />
        <el-table-column prop="detail" label="详情" show-overflow-tooltip />
        <el-table-column prop="clientIp" label="来源IP" width="130" />
        <el-table-column prop="traceId" label="TraceID" width="150" show-overflow-tooltip />
      </el-table>
      <el-empty v-if="!loading && items.length === 0" description="暂无审计日志" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { get } from '../api/request'

const loading = ref(false)
const items = ref<any[]>([])
const actionFilter = ref('')
const actions = ['LOGIN', 'LOGIN_FAIL', 'LOGOUT', 'CHANGE_PWD', 'EXPORT_REPORT', 'TASK_CREATE', 'TASK_STATUS', 'REPORT_AUDIT', 'PUSH_SEND', 'USER_MANAGE', 'DATASOURCE', 'KB_MANAGE']

function tagType(action: string): string {
  if (action.includes('FAIL') || action.includes('ERROR')) return 'danger'
  if (action.includes('PWD') || action.includes('LOGIN')) return 'warning'
  return 'info'
}

async function load() {
  loading.value = true
  try {
    const r = await get('/api/auth/audit-logs', { action: actionFilter.value || undefined, limit: 300 })
    items.value = r.data?.items ?? []
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-actions {
  display: flex;
  gap: 8px;
}
</style>
