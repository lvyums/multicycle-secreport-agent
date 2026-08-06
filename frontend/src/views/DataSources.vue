<template>
  <div class="datasources-page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span>数据源管理（零代码）</span>
          <el-button type="primary" size="small" @click="openCreate">新增数据源</el-button>
        </div>
      </template>

      <el-table :data="items" v-loading="loading" stripe>
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column label="类型" width="170">
          <template #default="{ row }">
            <el-tag size="small">{{ typeLabel(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-switch :model-value="row.status === 'enabled'" @change="() => onToggle(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="syncStrategy" label="同步策略" width="110" />
        <el-table-column prop="description" label="说明" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="onTest(row)">测试</el-button>
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="onRemove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑数据源' : '新增数据源'" width="560px">
      <el-form label-width="110px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如: 防火墙syslog" :disabled="!!editing" />
        </el-form-item>
        <el-form-item label="类型" required>
          <el-select v-model="form.type" placeholder="选择类型" style="width: 100%" :disabled="!!editing">
            <el-option v-for="(meta, key) in typeMeta" :key="key" :label="meta.label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item v-for="f in currentFields" :key="f.key" :label="f.label">
          <el-input v-model="form.config[f.key]" :type="f.type === 'password' ? 'password' : 'text'" />
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
        <el-button type="primary" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Api } from '@/api'

const loading = ref(false)
const items = ref<any[]>([])
const typeMeta = ref<Record<string, { label: string; fields: any[] }>>({})
const dialogVisible = ref(false)
const editing = ref<any>(null)
const form = ref<any>({ name: '', type: '', config: {}, syncStrategy: 'window', description: '' })

const currentFields = computed(() => {
  const meta = typeMeta.value[form.value.type]
  return meta?.fields || []
})

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
  const body = {
    name: form.value.name,
    type: form.value.type,
    config: form.value.config,
    syncStrategy: form.value.syncStrategy,
    description: form.value.description,
  }
  if (editing.value) {
    await Api.datasource.update({ id: editing.value.id, ...body })
  } else {
    await Api.datasource.create(body)
  }
  ElMessage.success('已保存')
  dialogVisible.value = false
  load()
}

async function onToggle(row: any) {
  const r = await Api.datasource.toggle(row.id)
  row.status = r.data.status
  ElMessage.success(row.status === 'enabled' ? '已启用' : '已停用')
}

async function onTest(row: any) {
  const r = await Api.datasource.test(row.id)
  if (r.data.ok) {
    ElMessage.success(`连通正常: ${r.data.message}`)
  } else {
    ElMessage.warning(`连通失败: ${r.data.message}`)
  }
}

async function onRemove(row: any) {
  await ElMessageBox.confirm(`确认删除数据源「${row.name}」？`, '提示', { type: 'warning' })
  await Api.datasource.remove(row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>
