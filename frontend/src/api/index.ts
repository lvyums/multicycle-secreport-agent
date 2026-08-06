/** API 模块 — 后端四组接口 + 数据源/健康检查 */
import { get, post } from './request'

export const Api = {
  // ── 健康检查 ──
  health: () => get('/health'),

  // ── 报告任务 ──
  report: {
    list: (params?: Record<string, string | number>) => get('/api/report/list', params),
    generate: (data: { cycle: string; windowStart?: string; windowEnd?: string }) =>
      post('/api/report/generate', data),
    detail: (taskId: number) => get(`/api/report/detail/${taskId}`),
    stats: () => get('/api/report/stats'),
  },

  // ── 调度 ──
  schedule: {
    list: () => get('/api/schedule/list'),
    nextRun: (cycle: string) => get('/api/schedule/next-run', { cycle }),
    trigger: (cycle: string) => post('/api/schedule/trigger', { cycle }),
    toggle: (enabled: boolean) => post('/api/schedule/toggle', { enabled }),
  },

  // ── 版本管理 ──
  version: {
    list: (params?: Record<string, string | number>) => get('/api/version/list', params),
    detail: (versionId: number) => get(`/api/version/detail/${versionId}`),
    content: (versionId: number) => get(`/api/version/content/${versionId}`),
    download: (versionId: number) => get(`/api/version/download/${versionId}`),
    // V1.2: 审核流转 + 版本对比
    audit: (action: string, versionId: number, data?: Record<string, unknown>) =>
      post(`/api/version/audit/${action}/${versionId}`, data || {}),
    auditHistory: (versionId: number) => get(`/api/version/audit/history/${versionId}`),
    compare: (baseId: number, targetId: number) =>
      get('/api/version/compare', { baseId, targetId }),
  },

  // ── 推送 ──
  publish: {
    push: (data: { versionId: number; channel?: string }) => post('/api/publish/push', data),
    records: (versionId: number) => get('/api/publish/records', { versionId }),
    channels: () => get('/api/publish/channels'),
  },

  // ── 数据源 ──
  datasource: {
    list: () => get('/api/datasource/list'),
    test: (id: number) => post('/api/datasource/test', { id }),
  },
}
