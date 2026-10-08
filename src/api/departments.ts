import { api, unwrapList } from './client'

export async function listDepartments(): Promise<string[]> {
  const data = await api<unknown>('/api/departments')
  const list = unwrapList<unknown>(data, ['departments', 'items', 'data', 'results'])
  return list
    .map((item) => {
      if (typeof item === 'string') return item
      if (item && typeof item === 'object') {
        const row = item as Record<string, unknown>
        if (typeof row.name === 'string') return row.name
        if (typeof row.department === 'string') return row.department
        if (typeof row.label === 'string') return row.label
      }
      return ''
    })
    .filter(Boolean)
}
