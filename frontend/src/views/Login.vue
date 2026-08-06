<template>
  <div class="login-page">
    <el-card class="login-card">
      <div class="login-brand">
        <el-icon :size="30" color="#409eff"><DataAnalysis /></el-icon>
        <h2>多周期网安报告智能体</h2>
        <p>安全运营报告自动生成 · 研判 · 推送平台</p>
      </div>
      <el-form :model="form" @keyup.enter="doLogin">
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" size="large" :prefix-icon="User" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" placeholder="密码" type="password" size="large" show-password :prefix-icon="Lock" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="doLogin">
            登 录
          </el-button>
        </el-form-item>
      </el-form>
      <div class="login-hint">
        演示账号：admin/admin123（管理员）· analyst/analyst123（分析师）· viewer/viewer123（只读）
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { post } from '../api/request'
import { setToken, setUser, type AuthUser } from '../utils/auth'

const router = useRouter()
const route = useRoute()
const form = reactive({ username: '', password: '' })
const loading = ref(false)

async function doLogin() {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  const r = await post<{ token: string; user: AuthUser }>('/api/auth/login', form)
  loading.value = false
  if (!r.success || !r.data) {
    ElMessage.error(r.msg || '登录失败')
    return
  }
  setToken(r.data.token)
  setUser(r.data.user)
  ElMessage.success(`欢迎，${r.data.user.displayName || r.data.user.username}`)
  router.replace((route.query.redirect as string) || '/dashboard')
}
</script>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  background: linear-gradient(135deg, #1d2129 0%, #2b3a55 100%);
}
.login-card {
  width: 380px;
  padding: 12px 8px;
}
.login-brand {
  text-align: center;
  margin-bottom: 20px;
}
.login-brand h2 {
  margin: 8px 0 4px;
  font-size: 20px;
}
.login-brand p {
  color: #909399;
  font-size: 13px;
  margin: 0;
}
.login-btn {
  width: 100%;
}
.login-hint {
  margin-top: 8px;
  color: #909399;
  font-size: 12px;
  line-height: 1.6;
}
</style>
