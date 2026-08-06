import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '任务看板' },
      },
      {
        path: 'reports',
        name: 'reports',
        component: () => import('@/views/Reports.vue'),
        meta: { title: '历史报告' },
      },
      {
        path: 'report-preview/:versionId?',
        name: 'report-preview',
        component: () => import('@/views/ReportPreview.vue'),
        meta: { title: '报告预览' },
      },
      {
        path: 'schedule',
        name: 'schedule',
        component: () => import('@/views/Schedule.vue'),
        meta: { title: '调度配置' },
      },
      {
        path: 'datasources',
        name: 'datasources',
        component: () => import('@/views/DataSources.vue'),
        meta: { title: '数据源管理' },
      },
      {
        path: 'knowledge',
        name: 'knowledge',
        component: () => import('@/views/Knowledge.vue'),
        meta: { title: '知识库' },
      },
      {
        path: 'report-config',
        name: 'report-config',
        component: () => import('@/views/ReportConfig.vue'),
        meta: { title: '报告选配' },
      },
      {
        path: 'task-logs',
        name: 'task-logs',
        component: () => import('@/views/TaskLogs.vue'),
        meta: { title: '任务日志' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = (to.meta?.title ? to.meta.title + ' - ' : '') + '多周期网安报告智能体'
})

export default router
