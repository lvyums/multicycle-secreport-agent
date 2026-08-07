/** fetch 统一封装 — 解析 ApiResponse{code, message, data, traceId}；自动注入 Bearer token（V2.0 RBAC） */
import type { ApiResponse } from '../types'
import { ElMessage } from 'element-plus'
import { getToken, clearAuth } from '../utils/auth'

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
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) {
    headers['Authorization'] = 'Bearer ' + token
  }
  const config: RequestInit = {
    method,
    headers,
    ...options,
  }

  if (data && method !== 'GET') {
    if (data instanceof FormData) {
      const h = { ...(config.headers as Record<string, string>) }
      delete h['Content-Type']
      config.headers = h
      config.body = data
    } else {
      config.body = JSON.stringify(data)
    }
  }

  try {
    const resp = await fetch(BASE + url, config)
    if (resp.status === 401 || resp.status === 403) {
      // 未登录/越权 → 清凭证回登录页
      clearAuth()
      if (!location.pathname.startsWith('/login')) {
        ElMessage.warning(resp.status === 401 ? '登录已过期，请重新登录' : '无权限访问该操作')
        location.href = '/login'
      }
      return { success: false, data: null, msg: resp.status === 401 ? '未登录' : '无权限' }
    }
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

export function put<T = any>(url: string, data?: any) {
  return request<T>('PUT', url, data)
}

/** 统一错误提示 */
export function notifyError(result: RequestResult) {
  if (!result.success) {
    ElMessage.error(result.msg || '请求失败')
  }
  return result
}
