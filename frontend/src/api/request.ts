/** fetch 统一封装 — 解析 ApiResponse{code, message, data, traceId} */
import type { ApiResponse } from '../types'
import { ElMessage } from 'element-plus'

const BASE = ''

export interface RequestResult<T = any> {
  success: boolean
  data: T | null
  msg: string
}

async function request<T = any>(
  method: string,
  url: string,
  data?: any,
  options?: RequestInit,
): Promise<RequestResult<T>> {
  const config: RequestInit = {
    method,
    headers: { 'Content-Type': 'application/json' },
    ...options,
  }

  if (data && method !== 'GET') {
    if (data instanceof FormData) {
      const headers = { ...(config.headers as Record<string, string>) }
      delete headers['Content-Type']
      config.headers = headers
      config.body = data
    } else {
      config.body = JSON.stringify(data)
    }
  }

  try {
    const resp = await fetch(BASE + url, config)
    if (!resp.ok) {
      return { success: false, data: null, msg: 'HTTP ' + resp.status }
    }
    const json = await resp.json()
    if (json.code === 0) {
      return { success: true, data: json.data, msg: json.message || 'success' }
    }
    return { success: false, data: null, msg: json.message || 'request failed' }
  } catch (err: any) {
    return { success: false, data: null, msg: '网络错误: ' + (err?.message || err) }
  }
}

export function get<T = any>(url: string, params?: Record<string, string | number>) {
  const query = params
    ? '?' + new URLSearchParams(Object.fromEntries(
        Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
      ) as Record<string, string>).toString()
    : ''
  return request<T>('GET', url + query)
}

export function post<T = any>(url: string, data?: any) {
  return request<T>('POST', url, data)
}

/** 统一错误提示 */
export function notifyError(result: RequestResult) {
  if (!result.success) {
    ElMessage.error(result.msg || '请求失败')
  }
  return result
}
