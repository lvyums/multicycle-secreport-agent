<template>
  <div class="user-manage">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>系统用户管理（V2.0 RBAC）</span>
          <el-button type="primary" size="small" @click="openCreate">新增用户</el-button>
        </div>
      </template>
      <el-table :data="users" v-loading="loading" border stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="用户名" min-width="140" />
        <el-table-column prop="displayName" label="姓名" min-width="120" />
        <el-table-column label="角色" width="130">
          <template #default="{ row }">
            <el-tag :type="roleType(row.role)" size="small">{{ roleLabel(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="enabled" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.enabled === 'enabled' ? 'success' : 'info'" size="small">
              {{ row.enabled === 'enabled' ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="createdAt" label="创建时间" width="170" />
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-popconfirm title="确认删除该用户？" @confirm="remove(row)">
              <template #reference>
                <el-button link type="danger" size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑用户' : '新增用户'" width="420px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="用户名" required>
          <el-input v-model="form.username" :disabled="!!editing" placeholder="登录用户名" />
        </el-form-item>
        <el-form-item v-if="!editing" label="密码" required>
          <el-input v-model="form.password" type="password" show-password placeholder="初始密码" />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="form.displayName" placeholder="显示名称" />
        </el-form-item>
        <el-form-item label="角色" required>
          <el-select v-model="form.role" style="width: 100%">
            <el-option label="系统管理员" value="admin" />
            <el-option label="安全分析师" value="analyst" />
            <el-option label="只读访客" value="viewer" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.enabled" active-value="enabled" inactive-value="disabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { get, post } from '../api/request'
import { notifyError } from '../api/request'

interface UserRow {
  id: number
  username: string
  displayName: string
  role: string
  enabled: string
  createdAt: string
}

const users = ref<UserRow[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const editing = ref<UserRow | null>(null)
const form = reactive({ username: '', password: '', displayName: '', role: 'viewer', enabled: 'enabled' })

const ROLE_LABELS: Record<string, string> = { admin: '系统管理员', analyst: '安全分析师', viewer: '只读访客' }
const roleLabel = (r: string) => ROLE_LABELS[r] || r
const roleType = (r: string) => (r === 'admin' ? 'danger' : r === 'analyst' ? 'warning' : 'info')

async function load() {
  loading.value = true
  const r = await get<{ items: UserRow[] }>('/api/auth/users')
  loading.value = false
  if (!r.success || !r.data) return notifyError(r)
  users.value = r.data.items
}

function openCreate() {
  editing.value = null
  Object.assign(form, { username: '', password: '', displayName: '', role: 'viewer', enabled: 'enabled' })
  dialogVisible.value = true
}

function openEdit(row: UserRow) {
  editing.value = row
  Object.assign(form, { username: row.username, password: '', displayName: row.displayName || '', role: row.role, enabled: row.enabled })
  dialogVisible.value = true
}

async function save() {
  if (!form.username) return ElMessage.warning('请输入用户名')
  if (!editing.value && !form.password) return ElMessage.warning('请输入初始密码')
  saving.value = true
  const url = editing.value ? '/api/auth/user/update' : '/api/auth/user/create'
  const body = editing.value
    ? { id: editing.value.id, displayName: form.displayName, role: form.role, enabled: form.enabled }
    : { username: form.username, password: form.password, displayName: form.displayName, role: form.role }
  const r = await post(url, body)
  saving.value = false
  if (!r.success) return notifyError(r)
  ElMessage.success('保存成功')
  dialogVisible.value = false
  load()
}

async function remove(row: UserRow) {
  const r = await post('/api/auth/user/delete', { id: row.id })
  if (!r.success) return notifyError(r)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
