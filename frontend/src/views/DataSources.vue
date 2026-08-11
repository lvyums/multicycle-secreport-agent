<template>
  <div class="datasources-page">
    <!-- 数据源健康看板（V2.8） -->
    <el-card class="mb16">
      <template #header>
        <div class="toolbar">
          <span>数据源健康看板</span>
          <el-button size="small" @click="loadHealth" :loading="healthLoading">刷新</el-button>
        </div>
      </template>

      <el-alert
        v-if="healthWarn"
        type="warning" :closable="false" class="mb12"
        :title="healthWarn"
      />

      <el-table :data="healthItems" size="small" v-loading="healthLoading" empty-text="暂无拉取记录">
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <span class="health-dot" :class="'dot-' + row.status" :title="statusLabel(row.status)"></span>
            <span class="health-text">{{ statusLabel(row.status) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="数据源" min-width="130" show-overflow-tooltip />
        <el-table-column prop="typeLabel" label="类型" width="120" />
        <el-table-column label="启用" width="70">
          <template #default="{ row }">
            <el-tag size="small" :type="row.enabled === 'enabled' ? 'success' : 'info'">
              {{ row.enabled === 'enabled' ? '启用' : (row.enabled === '-' ? '-' : '停用') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近 N 次拉取" width="160">
          <template #default="{ row }">
            <span class="ok-count">{{ row.okRuns }}</span>/{{ row.totalRuns }} 成功
            <span v-if="row.failRuns" class="fail-count">（{{ row.failRuns }} 失败）</span>
          </template>
        </el-table-column>
        <el-table-column label="成功率" width="90">
          <template #default="{ row }">{{ (row.okRatio * 100).toFixed(0) }}%</template>
        </el-table-column>
        <el-table-column label="最近拉取" min-width="200">
          <template #default="{ row }">
            <template v-if="row.latestAt">
              <el-tag v-if="row.latestOk" type="success" size="small">成功 {{ row.latestCount }} 条</el-tag>
              <el-tag v-else type="danger" size="small">失败</el-tag>
              <div class="test-time">{{ row.latestAt }}</div>
              <div v-if="!row.latestOk && row.latestError" class="err-msg">{{ row.latestError }}</div>
            </template>
            <span v-else class="muted">无记录</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card>
      <template #header>
        <div class="toolbar">
          <span>数据源管理（真实对接）</span>
          <el-button v-if="canManage" type="primary" size="small" @click="openCreate">新增数据源</el-button>
        </div>
      </template>

      <el-table :data="items" v-loading="loading" stripe>
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column label="类型" width="150">
          <template #default="{ row }">
            <el-tag size="small">{{ typeLabel(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-switch :model-value="row.status === 'enabled'" :disabled="!canManage" @change="() => onToggle(row)" />
          </template>
        </el-table-column>
        <el-table-column label="连通状态" width="170">
          <template #default="{ row }">
            <el-tag v-if="row.lastTest" :type="row.lastTest.ok ? 'success' : 'danger'" size="small">
              {{ row.lastTest.ok ? '连通正常' : '连接失败' }}
            </el-tag>
            <el-tag v-else type="info" size="small">未测试</el-tag>
            <div v-if="row.lastTest" class="test-time">{{ row.lastTest.at }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="syncStrategy" label="同步策略" width="110" />
        <el-table-column prop="description" label="说明" min-width="150" show-overflow-tooltip />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="onTest(row)">测试</el-button>
            <el-button v-if="canManage" link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canManage" link type="danger" size="small" @click="onRemove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑数据源' : '新增数据源'" width="620px">
      <el-form label-width="130px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如: 态势感知平台告警" :disabled="!!editing" />
        </el-form-item>
        <el-form-item label="类型" required>
          <el-select v-model="form.type" placeholder="选择类型" style="width: 100%" :disabled="!!editing" @change="onTypeChange">
            <el-option v-for="(meta, key) in typeMeta" :key="key" :label="meta.label" :value="key" />
          </el-select>
        </el-form-item>

        <!-- 对接指引 -->
        <el-alert v-if="currentMeta?.guide" :title="currentMeta.guide" type="info" :closable="false" class="guide-alert" />

        <el-form-item v-for="f in currentFields" :key="f.key" :label="f.label" :required="!!f.required">
          <el-select v-if="f.type === 'select'" v-model="form.config[f.key]" :placeholder="f.placeholder" style="width: 100%">
            <el-option v-for="opt in f.options || []" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
          <el-input
            v-else-if="f.type === 'password'"
            v-model="form.config[f.key]"
            :type="'password'"
            :placeholder="f.placeholder"
            show-password
          />
          <el-input
            v-else-if="f.type === 'textarea'"
            v-model="form.config[f.key]"
            type="textarea"
            :rows="2"
            :placeholder="f.placeholder"
          />
          <el-input v-else v-model="form.config[f.key]" :placeholder="f.placeholder" />
          <div v-if="f.help" class="field-help">{{ f.help }}</div>
        </el-form-item>

        <el-form-item label="同步策略">
          <el-select v-model="form.syncStrategy" style="width: 100%">
            <el-option label="按窗口拉取" value="window" />
            <el-option label="增量同步" value="incremental" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button v-if="editing?.id" :loading="testing" @click="onTest(editing)">测试连接</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Api } from '@/api'
import { isAdmin } from '@/utils/auth'

const canManage = isAdmin()

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const items = ref<any[]>([])
const typeMeta = ref<Record<string, any>>({})
const dialogVisible = ref(false)
const editing = ref<any>(null)
const form = ref<any>({ name: '', type: '', config: {}, syncStrategy: 'window', description: '' })

// ── 健康看板（V2.8） ──
const healthLoading = ref(false)
const healthItems = ref<any[]>([])
const healthWarn = ref('')

function statusLabel(s: string) {
  return { ok: '健康', warning: '异常', error: '故障', unknown: '未知' }[s] || s
}

async function loadHealth() {
  healthLoading.value = true
  try {
    const r = await Api.datasource.health()
    healthItems.value = r.data.items || []
    const bad = healthItems.value.filter((i: any) => i.status === 'error' || i.status === 'warning')
    healthWarn.value = bad.length
      ? `检测到 ${bad.length} 个数据源最近拉取异常（${bad.map((i: any) => i.name).join('、')}）。数据源故障可能导致 EMPTY 空报告，请先排查数据源再判定「无安全事件」。`
      : ''
  } finally {
    healthLoading.value = false
  }
}

const currentMeta = computed(() => typeMeta.value[form.value.type] || null)
const currentFields = computed(() => currentMeta.value?.fields || [])

const typeLabel = (t: string) => typeMeta.value[t]?.label || t

async function load() {
  loading.value = true
  try {
    const [meta, list] = await Promise.all([Api.datasource.meta(), Api.datasource.list()])
    typeMeta.value = meta.data.types
    items.value = list.data.items
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.value = { name: '', type: '', config: {}, syncStrategy: 'window', description: '' }
}

function onTypeChange() {
  // 切换类型清空配置（避免字段串味）
  form.value.config = {}
}

function openCreate() {
  editing.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: any) {
  editing.value = row
  form.value = {
    name: row.name,
    type: row.type,
    config: { ...(row.config || {}) },
    syncStrategy: row.syncStrategy || 'window',
    description: row.description || '',
  }
  dialogVisible.value = true
}

async function onSave() {
  if (!form.value.name || !form.value.type) {
    ElMessage.warning('名称与类型必填')
    return
  }
  const missing = currentFields.value.filter((f: any) => f.required && !form.value.config[f.key])
  if (missing.length) {
    ElMessage.warning(`请填写必填字段: ${missing.map((f: any) => f.label).join('、')}`)
    return
  }
  saving.value = true
  try {
    const body = {
      name: form.value.name,
      type: form.value.type,
      config: form.value.config,
      syncStrategy: form.value.syncStrategy,
      description: form.value.description,
    }
    let id = editing.value?.id
    if (editing.value) {
      await Api.datasource.update({ id: editing.value.id, ...body })
    } else {
      const r = await Api.datasource.create(body)
      id = r.data.id
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    await load()
    // 新建后立即测连通，引导用户确认对接成功
    if (!editing.value && id) {
      const row = items.value.find((i: any) => i.id === id)
      if (row) await onTest(row)
    }
  } finally {
    saving.value = false
  }
}

async function onToggle(row: any) {
  const r = await Api.datasource.toggle(row.id)
  row.status = r.data.status
  ElMessage.success(row.status === 'enabled' ? '已启用' : '已停用')
}

async function onTest(row: any) {
  testing.value = true
  try {
    const r = await Api.datasource.test(row.id)
    row.lastTest = { ok: r.data.ok, msg: r.data.message, at: new Date().toLocaleString() }
    if (r.data.ok) {
      ElMessage.success(`连通正常: ${r.data.message}`)
    } else {
      ElMessage.warning(`连通失败: ${r.data.message}`)
    }
  } finally {
    testing.value = false
  }
}

async function onRemove(row: any) {
  await ElMessageBox.confirm(`确认删除数据源「${row.name}」？`, '提示', { type: 'warning' })
  await Api.datasource.remove(row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(() => {
  load()
  loadHealth()
})
</script>

<style scoped>
.mb16 {
  margin-bottom: 16px;
}
.mb12 {
  margin-bottom: 12px;
}
.guide-alert {
  margin-bottom: 16px;
}
.field-help {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
  margin-top: 2px;
}
.test-time {
  font-size: 11px;
  color: #b0b3b8;
  margin-top: 2px;
}
.err-msg {
  font-size: 11px;
  color: #f56c6c;
  margin-top: 2px;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.muted {
  color: #c0c4cc;
}
.ok-count {
  color: #67c23a;
  font-weight: 600;
}
.fail-count {
  color: #f56c6c;
}
.health-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}
.dot-ok {
  background: #67c23a;
}
.dot-warning {
  background: #e6a23c;
}
.dot-error {
  background: #f56c6c;
}
.dot-unknown {
  background: #c0c4cc;
}
.health-text {
  font-size: 13px;
  vertical-align: middle;
}
</style>
