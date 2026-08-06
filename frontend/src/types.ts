/** 统一后端响应结构 */
export interface ApiResponse<T = any> {
  code: number
  message: string
  data: T
  traceId: string
  timestamp: number
}

/** 分页结构 */
export interface PageResult<T> {
  items: T[]
  total: number
}

/** 报告任务 */
export interface ReportTask {
  id: number
  cycle: string
  cycleLabel?: string
  windowStart: string
  windowEnd: string
  status: string
  statusLabel?: string
  triggerType: string
  errorMsg?: string
  durationMs?: number
  createdAt: string
}

/** 报告版本 */
export interface ReportVersion {
  id: number
  taskId: number
  cycle: string
  cycleLabel?: string
  windowStart: string
  windowEnd: string
  versionNo: number
  versionType: string
  status: string
  title: string
  filePath: string
  createdAt: string
}

/** 周期枚举 */
export const CYCLE_LABELS: Record<string, string> = {
  DAILY: '日报',
  WEEKLY: '周报',
  MONTHLY: '月报',
  QUARTERLY: '季报',
  YEARLY: '年报',
}

export const TASK_STATUS_LABELS: Record<string, string> = {
  PENDING: '待执行',
  RUNNING: '执行中',
  SUCCESS: '成功',
  EMPTY: '无数据',
  FAILED: '失败',
  PARTIAL: '部分成功',
}

export const VERSION_STATUS_LABELS: Record<string, string> = {
  DRAFT: '初稿',
  REVIEWING: '审核中',
  APPROVED: '终审',
  ARCHIVED: '已归档',
  FAILED: '失败',
}
