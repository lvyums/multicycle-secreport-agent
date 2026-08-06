<template>
  <div class="kb-page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span>知识库文档</span>
          <div class="right">
            <el-select v-model="category" placeholder="全部分类" clearable style="width: 150px" @change="load">
              <el-option v-for="c in categories" :key="c" :label="catLabel(c)" :value="c" />
            </el-select>
            <el-button v-if="canManage" type="primary" size="small" @click="openCreate">新增文档</el-button>
          </div>
        </div>
      </template>

      <el-table :data="items" v-loading="loading" stripe>
        <el-table-column prop="title" label="标题" min-width="180" />
        <el-table-column label="分类" width="130">
          <template #default="{ row }">
            <el-tag size="small">{{ catLabel(row.category) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-switch :model-value="row.enabled === 'enabled'" :disabled="!canManage" @change="() => onToggle(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="updatedAt" label="更新时间" width="170" />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button v-if="canManage" link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canManage" link type="danger" size="small" @click="onRemove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑文档' : '新增文档'" width="640px">
      <el-form label-width="80px">
        <el-form-item label="标题" required>
          <el-input v-model="form.title" placeholder="如: SSH 爆破攻击研判参考" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" style="width: 100%">
            <el-option v-for="c in categories" :key="c" :label="catLabel(c)" :value="c" />
          </el-select>
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="form.content" type="textarea" :rows="8"
            placeholder="研判参考内容，报告生成时注入 LLM 提示词（最多 5 篇启用文档）" />
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
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Api } from '@/api'
import { isAdmin } from '@/utils/auth'

const canManage = isAdmin()

const loading = ref(false)
const items = ref<any[]>([])
const categories = ref<string[]>([])
const category = ref('')
const dialogVisible = ref(false)
const editing = ref<any>(null)
const form = ref<any>({ title: '', category: 'general', content: '' })

const CAT_LABELS: Record<string, string> = {
  general: '通用', attack: '攻击研判', defense: '防护处置', regulation: '合规要求',
}
const catLabel = (c: string) => CAT_LABELS[c] || c

async function load() {
  loading.value = true
  try {
    const r = await Api.kb.list(category.value || undefined)
    items.value = r.data.items
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.value = { title: '', category: 'general', content: '' }
}

function openCreate() {
  editing.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: any) {
  editing.value = row
  form.value = { title: row.title, category: row.category, content: row.content }
  dialogVisible.value = true
}

async function onSave() {
  if (!form.value.title) {
    ElMessage.warning('标题必填')
    return
  }
  if (editing.value) {
    await Api.kb.update({ id: editing.value.id, ...form.value })
  } else {
    await Api.kb.create(form.value)
  }
  ElMessage.success('已保存')
  dialogVisible.value = false
  load()
}

async function onToggle(row: any) {
  const r = await Api.kb.toggle(row.id)
  row.enabled = r.data.enabled
  ElMessage.success(row.enabled === 'enabled' ? '已启用（将注入研判）' : '已停用')
}

async function onRemove(row: any) {
  await ElMessageBox.confirm(`确认删除文档「${row.title}」？`, '提示', { type: 'warning' })
  await Api.kb.remove(row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(async () => {
  const r = await Api.kb.categories()
  categories.value = r.data.categories
  load()
})
</script>
