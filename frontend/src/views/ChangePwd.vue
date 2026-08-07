<template>
  <div class="change-pwd-page">
    <el-card class="change-pwd-card">
      <div class="brand">
        <el-icon :size="30" color="#409eff"><Lock /></el-icon>
        <h2>修改密码</h2>
        <p v-if="forced">出于安全要求，首次登录须修改初始密码后才能使用系统</p>
      </div>
      <el-form :model="form" label-position="top" @keyup.enter="doChange">
        <el-form-item label="旧密码">
          <el-input v-model="form.oldPwd" type="password" show-password placeholder="请输入当前密码" />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="form.newPwd" type="password" show-password placeholder="至少 8 位，含字母与数字" />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="form.confirm" type="password" show-password placeholder="再次输入新密码" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="large" class="submit-btn" :loading="loading" @click="doChange">
            确认修改
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { post } from '../api/request'
import { clearAuth, markPwdChanged } from '../utils/auth'

const router = useRouter()
const forced = ref(true)
const loading = ref(false)
const form = reactive({ oldPwd: '', newPwd: '', confirm: '' })

async function doChange() {
  if (!form.oldPwd || !form.newPwd) {
    ElMessage.warning('请输入旧密码与新密码')
    return
  }
  if (form.newPwd !== form.confirm) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  loading.value = true
  const r = await post('/api/auth/change-pwd', { oldPwd: form.oldPwd, newPwd: form.newPwd })
  loading.value = false
  if (!r.success) {
    ElMessage.error(r.msg || '修改失败')
    return
  }
  ElMessage.success('密码修改成功，请重新登录')
  markPwdChanged()
  clearAuth()
  router.replace('/login')
}
</script>

<style scoped>
.change-pwd-page {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  background: linear-gradient(135deg, #1d2129 0%, #2b3a55 100%);
}
.change-pwd-card {
  width: 380px;
  padding: 12px 8px;
}
.brand {
  text-align: center;
  margin-bottom: 20px;
}
.brand h2 {
  margin: 8px 0 4px;
  font-size: 20px;
}
.brand p {
  color: #909399;
  font-size: 12px;
  margin: 0;
}
.submit-btn {
  width: 100%;
}
</style>
