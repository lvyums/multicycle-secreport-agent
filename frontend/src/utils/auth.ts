/** 认证状态管理（V2.0 RBAC）— token + 用户信息 localStorage */
export interface AuthUser {
  id: number
  username: string
  role: string
  displayName: string
}

const TOKEN_KEY = 'sec_report_token'
const USER_KEY = 'sec_report_user'

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function getUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as AuthUser
  } catch {
    return null
  }
}

export function setUser(user: AuthUser) {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function isLoggedIn(): boolean {
  return !!getToken()
}

export function hasRole(...roles: string[]): boolean {
  const u = getUser()
  return !!u && roles.includes(u.role)
}

export function isAdmin(): boolean {
  return hasRole('admin')
}

export const ROLE_LABEL: Record<string, string> = {
  admin: '系统管理员',
  analyst: '安全分析师',
  viewer: '只读访客',
}
