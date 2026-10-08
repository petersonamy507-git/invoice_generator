import { api, unwrapList } from './client'
import type { ApiUser, UserCreate, UserPasswordUpdate, UserUpdate } from './types'

export const teamUsers = {
  list: async () => {
    const data = await api<{ users?: ApiUser[] } | ApiUser[]>('/api/users')
    return unwrapList<ApiUser>(data, ['users', 'items', 'data', 'results'])
  },
  create: (body: UserCreate) =>
    api<ApiUser>('/api/users', { method: 'POST', body: JSON.stringify(body) }),
  update: (id: number, body: UserUpdate) =>
    api<ApiUser>(`/api/users/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  setPassword: (id: number, body: UserPasswordUpdate) =>
    api<{ id: number; password_updated: boolean }>(`/api/users/${id}/password`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  remove: (id: number) =>
    api<{ id: number; deleted: boolean }>(`/api/users/${id}`, { method: 'DELETE' }),
}
