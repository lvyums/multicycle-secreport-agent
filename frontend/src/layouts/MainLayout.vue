<template>
  <el-container class="main-layout">
    <el-aside width="220px" class="main-aside">
      <div class="brand">
        <el-icon :size="22"><DataAnalysis /></el-icon>
        <span>多周期网安报告</span>
      </div>
      <el-menu :default-active="activeMenu" router class="main-menu">
        <el-menu-item index="/dashboard">
          <el-icon><Odometer /></el-icon>
          <span>任务看板</span>
        </el-menu-item>
        <el-menu-item index="/reports">
          <el-icon><Document /></el-icon>
          <span>历史报告</span>
        </el-menu-item>
        <el-menu-item index="/schedule">
          <el-icon><Timer /></el-icon>
          <span>调度配置</span>
        </el-menu-item>
        <el-menu-item index="/datasources">
          <el-icon><Connection /></el-icon>
          <span>数据源管理</span>
        </el-menu-item>
        <el-menu-item index="/knowledge">
          <el-icon><Collection /></el-icon>
          <span>知识库</span>
        </el-menu-item>
        <el-menu-item index="/report-config">
          <el-icon><Setting /></el-icon>
          <span>报告选配</span>
        </el-menu-item>
        <el-menu-item index="/task-logs">
          <el-icon><Tickets /></el-icon>
          <span>任务日志</span>
        </el-menu-item>
        <el-menu-item v-if="canManage" index="/users">
          <el-icon><UserFilled /></el-icon>
          <span>系统用户</span>
        </el-menu-item>
        <el-menu-item v-if="canManage" index="/audit">
          <el-icon><List /></el-icon>
          <span>审计日志</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="main-header">
        <div class="header-title">{{ pageTitle }}</div>
        <div class="header-right">
          <el-tag size="small" type="info">V2.0 生产加固</el-tag>
          <el-dropdown @command="onCommand">
            <span class="user-chip">
              <el-icon><UserFilled /></el-icon>
              {{ user?.displayName || user?.username || '未登录' }}
              <el-tag size="small" :type="roleTagType" class="role-tag">{{ roleLabel }}</el-tag>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getUser, clearAuth, isAdmin, ROLE_LABEL } from '../utils/auth'

const route = useRoute()
const router = useRouter()
const user = getUser()
const canManage = isAdmin()
const activeMenu = computed(() => route.path)
const pageTitle = computed(() => (route.meta?.title as string) || '')
const roleLabel = computed(() => (user ? (ROLE_LABEL[user.role] || user.role) : ''))
const roleTagType = computed(() => (user?.role === 'admin' ? 'danger' : user?.role === 'analyst' ? 'warning' : 'info'))

function onCommand(cmd: string) {
  if (cmd === 'logout') {
    clearAuth()
    router.replace('/login')
  }
}
</script>

<style scoped>
.main-layout {
  height: 100%;
}
.main-aside {
  background: #1d2129;
  color: #fff;
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 56px;
  padding: 0 16px;
  color: #fff;
  font-weight: 600;
  font-size: 15px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.main-menu {
  border-right: none;
  background: transparent;
}
.main-menu :deep(.el-menu-item) {
  color: rgba(255, 255, 255, 0.72);
}
.main-menu :deep(.el-menu-item.is-active) {
  color: #409eff;
  background: rgba(64, 158, 255, 0.12);
}
.main-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
}
.header-title {
  font-size: 16px;
  font-weight: 600;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.user-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: #303133;
  font-size: 14px;
}
.role-tag {
  margin-left: 2px;
}
.main-content {
  background: #f5f7fa;
}
</style>
