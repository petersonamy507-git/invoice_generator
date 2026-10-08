import { api } from './client'
import type { ApiUser } from './types'

export interface LoginResponse {
  user: ApiUser
}

export interface MeResponse {
  authenticated: boolean
  user: ApiUser | null
}

export const auth = {
  login: (identifier: string, password: string) =>
    api<LoginResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ identifier, password }),
    }),
  me: () => api<MeResponse>('/api/auth/me'),
  logout: () => api<{ ok?: boolean }>('/api/auth/logout', { method: 'POST' }),
}

export const login = auth.login
export const getMe = auth.me
export const logout = auth.logout
