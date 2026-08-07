import { createRouter, createWebHistory } from 'vue-router'
import { isLoggedIn, needsChangePwd, getUser } from '../utils/auth'

// V2.3 路由级角色拦截：meta.roles 声明可访问角色（viewer < analyst < admin）
const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录' },
  },
  {
    path: '/change-pwd',
    name: 'change-pwd',
    component: () => import('@/views/ChangePwd.vue'),
    meta: { title: '修改密码' },
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '任务看板', roles: ['viewer', 'analyst', 'admin'] },
      },
      {
        path: 'reports',
        name: 'reports',
        component: () => import('@/views/Reports.vue'),
        meta: { title: '历史报告', roles: ['viewer', 'analyst', 'admin'] },
      },
      {
        path: 'report-preview/:versionId?',
        name: 'report-preview',
        component: () => import('@/views/ReportPreview.vue'),
        meta: { title: '报告预览', roles: ['viewer', 'analyst', 'admin'] },
      },
      {
        path: 'schedule',
        name: 'schedule',
        component: () => import('@/views/Schedule.vue'),
        meta: { title: '调度配置', roles: ['viewer', 'analyst', 'admin'] },
      },
      {
        path: 'datasources',
        name: 'datasources',
        component: () => import('@/views/DataSources.vue'),
        meta: { title: '数据源管理', roles: ['admin'] },
      },
      {
        path: 'knowledge',
        name: 'knowledge',
        component: () => import('@/views/Knowledge.vue'),
        meta: { title: '知识库', roles: ['admin'] },
      },
      {
        path: 'report-config',
        name: 'report-config',
        component: () => import('@/views/ReportConfig.vue'),
        meta: { title: '报告选配', roles: ['admin'] },
      },
      {
        path: 'task-logs',
        name: 'task-logs',
        component: () => import('@/views/TaskLogs.vue'),
        meta: { title: '任务日志', roles: ['viewer', 'analyst', 'admin'] },
      },
      {
        path: 'users',
        name: 'users',
        component: () => import('@/views/UserManage.vue'),
        meta: { title: '系统用户', roles: ['admin'] },
      },
      {
        path: 'audit',
        name: 'audit',
        component: () => import('@/views/AuditLog.vue'),
        meta: { title: '审计日志', roles: ['admin'] },
      },
      {
        path: '403',
        name: 'forbidden',
        component: () => import('@/views/Forbidden.vue'),
        meta: { title: '无权限' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (to.path !== '/login' && !isLoggedIn()) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.path === '/login' && isLoggedIn()) {
    return { path: '/dashboard' }
  }
  // V2.2：强制改密——未改密用户只能访问改密页
  if (to.path !== '/change-pwd' && needsChangePwd()) {
    return { path: '/change-pwd' }
  }
  if (to.path === '/change-pwd' && !needsChangePwd() && isLoggedIn()) {
    return { path: '/dashboard' }
  }
  // V2.3：路由级角色拦截（后端 403 兜底，前端防页面壳直输）
  const roles: string[] | undefined = to.meta?.roles as string[] | undefined
  if (roles && roles.length > 0) {
    const role = getUser()?.role || ''
    if (!roles.includes(role)) {
      return { path: '/403' }
    }
  }
  return true
})

router.afterEach((to) => {
  document.title = (to.meta?.title ? to.meta.title + ' - ' : '') + '多周期网安报告智能体'
})

export default router
