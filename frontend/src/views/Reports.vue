<template>
  <el-card>
    <template #header>
      <div class="toolbar">
        <span>历史报告</span>
        <div>
          <el-select v-model="cycleFilter" placeholder="全部周期" clearable style="width: 130px" @change="load">
            <el-option v-for="(label, value) in CYCLE_LABELS" :key="value" :label="label" :value="value" />
          </el-select>
          <el-button style="margin-left: 8px" type="primary" plain @click="openBatch">批量导出 ZIP</el-button>
          <el-button style="margin-left: 8px" @click="load">刷新</el-button>
        </div>
      </div>
    </template>

    <el-table :data="versions" v-loading="loading" empty-text="暂无报告版本">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column label="周期" width="90">
        <template #default="{ row }">
          <el-tag size="small">{{ CYCLE_LABELS[row.cycle] || row.cycle }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="标题" min-width="240" show-overflow-tooltip />
      <el-table-column prop="summary" label="摘要" min-width="240" show-overflow-tooltip />
      <el-table-column label="版本" width="80">
        <template #default="{ row }">v{{ row.versionNo }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="statusType(row.status)">{{ VERSION_STATUS_LABELS[row.status] || row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="createdAt" label="生成时间" width="170" />
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="preview(row.id)">预览</el-button>
          <el-button size="small" link type="success" @click="download(row.id)">下载</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      class="mt16"
      layout="total, prev, pager, next"
      :total="total"
      :page-size="pageSize"
      :current-page="page"
      @current-change="onPage"
    />

    <!-- 批量导出 / 周期归档（V2.8） -->
    <el-dialog v-model="batchVisible" title="批量导出 ZIP（周期归档）" width="460px">
      <el-form label-width="90px">
        <el-form-item label="报告周期" required>
          <el-select v-model="batchForm.cycle" placeholder="选择周期" style="width: 100%">
            <el-option v-for="(label, value) in CYCLE_LABELS" :key="value" :label="label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="窗口范围">
          <div class="range-row">
            <el-date-picker
              v-model="batchForm.from" type="date" value-format="YYYY-MM-DD"
              placeholder="开始日期（含）" style="width: 100%"
            />
            <span class="range-sep">~</span>
            <el-date-picker
              v-model="batchForm.to" type="date" value-format="YYYY-MM-DD"
              placeholder="结束日期（含）" style="width: 100%"
            />
          </div>
          <div class="hint">不选范围 = 导出该周期全部版本（最多 200 份）。用于月度/季度归档留痕。</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchLoading" @click="doBatchExport">导出并下载</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Api } from '@/api'
import { notifyError } from '@/api/request'
import { CYCLE_LABELS, VERSION_STATUS_LABELS } from '@/types'
import type { ReportVersion } from '@/types'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const versions = ref<ReportVersion[]>([])
const cycleFilter = ref('')
const page = ref(1)
const pageSize = 15
const total = ref(0)

// ── 批量导出（V2.8） ──
const batchVisible = ref(false)
const batchLoading = ref(false)
const batchForm = ref<{ cycle: string; from: string; to: string }>({ cycle: '', from: '', to: '' })

function openBatch() {
  batchForm.value = { cycle: cycleFilter.value || '', from: '', to: '' }
  batchVisible.value = true
}

async function doBatchExport() {
  if (!batchForm.value.cycle) {
    ElMessage.warning('请选择报告周期')
    return
  }
  batchLoading.value = true
  try {
    // request.ts 只解析 JSON，ZIP 需手动 fetch 带 token 拿 blob
    const { getToken } = await import('@/utils/auth')
    const resp = await fetch('/api/report/export-batch', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + getToken(),
      },
      body: JSON.stringify(batchForm.value),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => null)
      ElMessage.error(err?.message || 'HTTP ' + resp.status)
      return
    }
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    const cd = resp.headers.get('Content-Disposition') || ''
    const m = cd.match(/filename\*=UTF-8''(.+)/)
    a.href = url
    a.download = m ? decodeURIComponent(m[1]) : 'report-archive.zip'
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    ElMessage.success('批量导出已开始，ZIP 已下载')
    batchVisible.value = false
  } catch (e: any) {
    ElMessage.error('导出失败: ' + (e?.message || e))
  } finally {
    batchLoading.value = false
  }
}

function statusType(s: string) {
  return { DRAFT: 'warning', APPROVED: 'success', ARCHIVED: 'info', FAILED: 'danger', REVIEWING: 'primary' }[s] || 'info'
}

async function load() {
  loading.value = true
  const params: Record<string, string | number> = { page: page.value, limit: pageSize }
  if (cycleFilter.value) params.cycle = cycleFilter.value
  const r = await Api.version.list(params)
  notifyError(r)
  if (r.success) {
    versions.value = (r.data as any)?.items || []
    total.value = (r.data as any)?.total || 0
  }
  loading.value = false
}

function onPage(p: number) {
  page.value = p
  load()
}

function preview(versionId: number) {
  router.push(`/report-preview/${versionId}`)
}

async function download(versionId: number) {
  // 后端返回 FileResponse 文件流，直接触发浏览器下载
  const a = document.createElement('a')
  a.href = `/api/version/download/${versionId}`
  a.download = ''
  document.body.appendChild(a)
  a.click()
  a.remove()
  ElMessage.success('下载已开始')
}

onMounted(() => {
  const taskId = route.query.taskId
  if (taskId) {
    ElMessage.info(`任务 #${taskId} 的版本列表`)
  }
  load()
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
  justify-content: flex-end;
}
.range-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}
.range-sep {
  color: #909399;
}
.hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
  margin-top: 4px;
}
</style>
