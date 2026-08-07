/** API 模块 — 后端全部接口分组 */
import { get, post } from './request'

export const Api = {
  // ── 健康检查 ──
  health: () => get('/health'),

  // ── 认证（V2.2 含改密） ──
  auth: {
    login: (data: { username: string; password: string }) => post('/api/auth/login', data),
    me: () => get('/api/auth/me'),
    changePwd: (data: { oldPwd: string; newPwd: string }) => post('/api/auth/change-pwd', data),
    users: () => get('/api/auth/users'),
    createUser: (data: Record<string, unknown>) => post('/api/auth/users/create', data),
    toggleUser: (id: number) => post('/api/auth/users/toggle', { id }),
    resetPwd: (data: { id: number; password: string }) => post('/api/auth/users/reset-pwd', data),
  },

  // ── 报告任务 ──
  report: {
    list: (params?: Record<string, string | number>) => get('/api/report/list', params),
    generate: (data: { cycle: string; windowStart?: string; windowEnd?: string; rerun?: boolean }) =>
      post('/api/report/generate', data),
    detail: (taskId: number) => get(`/api/report/detail/${taskId}`),
    status: (taskId: number) => get(`/api/report/status/${taskId}`),
    stats: () => get('/api/report/stats'),
    // V2.1 智能问答 + 导出
    qa: (data: { versionId: number; question: string }) => post('/api/report/qa', data),
    exportUrl: (versionId: number, format: 'md' | 'docx') =>
      `/api/report/export/${versionId}?format=${format}`,
  },

  // ── 调度 ──
  schedule: {
    list: () => get('/api/schedule/list'),
    get: () => get('/api/schedule/get'),
    nextRun: (cycle: string) => get('/api/schedule/next-run', { cycle }),
    trigger: (cycle: string) => post('/api/schedule/trigger', { cycle }),
    toggle: (enabled: boolean) => post('/api/schedule/toggle', { enabled }),
    save: (body: Record<string, unknown>) => post('/api/schedule/save', body),
    pause: (body: Record<string, unknown>) => post('/api/schedule/pause', body),
  },

  // ── 数据源（V1.3 零代码管理） ──
  datasource: {
    meta: () => get('/api/datasource/meta'),
    list: () => get('/api/datasource/list'),
    create: (body: Record<string, unknown>) => post('/api/datasource/create', body),
    update: (body: Record<string, unknown>) => post('/api/datasource/update', body),
    toggle: (id: number) => post('/api/datasource/toggle', { id }),
    remove: (id: number) => post('/api/datasource/delete', { id }),
    test: (id: number) => post('/api/datasource/test', { id }),
  },

  // ── 知识库（V1.3） ──
  kb: {
    categories: () => get('/api/kb/categories'),
    list: (category?: string) => get('/api/kb/list', category ? { category } : undefined),
    create: (body: Record<string, unknown>) => post('/api/kb/create', body),
    update: (body: Record<string, unknown>) => post('/api/kb/update', body),
    toggle: (id: number) => post('/api/kb/toggle', { id }),
    remove: (id: number) => post('/api/kb/delete', { id }),
  },

  // ── 报告选配（V1.3） ──
  config: {
    reportGet: () => get('/api/config/report/get'),
    reportSave: (body: Record<string, unknown>) => post('/api/config/report/save', body),
  },

  // ── 版本管理 ──
  version: {
    list: (params?: Record<string, string | number>) => get('/api/version/list', params),
    detail: (versionId: number) => get(`/api/version/detail/${versionId}`),
    content: (versionId: number) => get(`/api/version/content/${versionId}`),
    download: (versionId: number) => get(`/api/version/download/${versionId}`),
    compare: (baseId: number, targetId: number) => get('/api/version/compare', { baseId, targetId }),
    audit: (action: string, versionId: number, body: Record<string, unknown>) =>
      post(`/api/version/audit/${action}/${versionId}`, body),
    history: (versionId: number) => get(`/api/version/audit/history/${versionId}`),
  },

  // ── 推送 ──
  publish: {
    push: (data: { versionId: number; channel?: string }) => post('/api/publish/push', data),
    records: (versionId: number) => get('/api/publish/records', { versionId }),
    channels: () => get('/api/publish/channels'),
  },
}
