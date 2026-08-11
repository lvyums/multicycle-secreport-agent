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
        <el-menu-item index="/trend">
          <el-icon><TrendCharts /></el-icon>
          <span>趋势分析</span>
        </el-menu-item>
        <el-menu-item index="/timeline">
          <el-icon><Histogram /></el-icon>
          <span>报告时间轴</span>
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
        <el-menu-item v-if="canManage" index="/alert-rules">
          <el-icon><Bell /></el-icon>
          <span>告警规则</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="main-header">
        <div class="header-title">{{ pageTitle }}</div>
        <div class="header-right">
          <el-tag size="small" type="info">V2.8</el-tag>
          <el-popover placement="bottom-end" :width="360" trigger="click" @show="loadNotifications">
            <template #reference>
              <el-badge :value="unreadCount" :hidden="unreadCount === 0" :max="99" class="bell-badge">
                <el-icon :size="18" class="bell-icon"><Bell /></el-icon>
              </el-badge>
            </template>
            <div class="notify-panel">
              <div class="notify-head">
                <span>通知中心</span>
                <el-button link type="primary" size="small" @click="onReadAll">全部已读</el-button>
              </div>
              <el-empty v-if="notifications.length === 0" description="暂无通知" :image-size="60" />
              <div v-else class="notify-list">
                <div v-for="n in notifications" :key="n.id" class="notify-item"
                     :class="{ unread: n.readFlag === 'no' }" @click="onRead(n)">
                  <div class="notify-title">
                    <el-tag size="small" :type="levelType(n.level)" effect="plain">{{ typeLabel(n.type) }}</el-tag>
                    <span>{{ n.title }}</span>
                    <el-icon v-if="n.readFlag === 'no'" class="dot"><BellFilled /></el-icon>
                  </div>
                  <div class="notify-content">{{ n.content }}</div>
                  <div class="notify-time">{{ n.createdAt }}</div>
                </div>
              </div>
            </div>
          </el-popover>
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
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bell, BellFilled } from '@element-plus/icons-vue'
import { getUser, clearAuth, isAdmin, ROLE_LABEL } from '../utils/auth'
import { Api } from '../api'

const route = useRoute()
const router = useRouter()
const user = getUser()
const unreadCount = ref(0)
const notifications = ref<any[]>([])
let timer: number | undefined

const typeLabel = (t: string) =>
  ({ REPORT_READY: '待审核', PUSH_FAIL: '推送失败', ALERT: '告警', REVIEW_RESULT: '审核' }[t] || t)
const levelType = (l: string) =>
  ({ info: 'info', warning: 'warning', error: 'danger' }[l] || 'info')

async function loadNotifications() {
  try {
    const r = await Api.notification.list({ limit: 10 })
    notifications.value = r.data.items || []
  } catch { /* 静默 */ }
}

async function refreshUnread() {
  try {
    const r = await Api.notification.unreadCount()
    unreadCount.value = r.data.count || 0
  } catch { /* 静默 */ }
}

async function onRead(n: any) {
  if (n.readFlag === 'no') {
    try { await Api.notification.read(n.id) } catch { /* 静默 */ }
    n.readFlag = 'yes'
    refreshUnread()
  }
}

async function onReadAll() {
  try {
    await Api.notification.readAll()
    notifications.value.forEach((n) => (n.readFlag = 'yes'))
    refreshUnread()
  } catch { /* 静默 */ }
}

onMounted(() => {
  refreshUnread()
  timer = window.setInterval(refreshUnread, 30000)
})
onUnmounted(() => {
  if (timer) window.clearInterval(timer)
})
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
.bell-badge {
  cursor: pointer;
  margin-right: 4px;
  display: inline-flex;
  align-items: center;
}
.bell-icon {
  color: #606266;
  vertical-align: middle;
}
.notify-panel {
  max-height: 420px;
  display: flex;
  flex-direction: column;
}
.notify-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
}
.notify-list {
  overflow-y: auto;
  max-height: 340px;
}
.notify-item {
  padding: 8px 4px;
  border-bottom: 1px solid #f5f5f5;
  cursor: pointer;
}
.notify-item.unread {
  background: #f5f9ff;
}
.notify-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}
.notify-title .dot {
  color: #f56c6c;
}
.notify-content {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.notify-time {
  font-size: 11px;
  color: #c0c4cc;
  margin-top: 2px;
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
