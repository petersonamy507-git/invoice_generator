import { api, unwrapList } from './client'

export async function listClubbing(department?: string) {
  const query = department ? `?department=${encodeURIComponent(department)}` : ''
  return api<unknown>(`/api/clubbing${query}`)
}

export async function listInvoiceHistory(params?: {
  employee_id?: string
  department?: string
  limit?: number
}) {
  const search = new URLSearchParams()
  if (params?.employee_id) search.set('employee_id', params.employee_id)
  if (params?.department) search.set('department', params.department)
  if (params?.limit) search.set('limit', String(params.limit))
  const query = search.toString() ? `?${search}` : ''
  const data = await api<unknown>(`/api/invoice-history${query}`)
  return unwrapList(data, ['history', 'items', 'data', 'results'])
}

export { listInvoiceTemplates, getTemplatesStatus } from './templates'

export function getCategoriesStatus() {
  return api<unknown>('/api/categories/status')
}

export function getHealth() {
  return api<{ status: string; service?: string; version?: string }>('/api/health')
}
