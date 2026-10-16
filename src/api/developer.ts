import { apiRequest } from './client'

export interface DevTableInfo {
  name: string
  approx_rows?: number | null
  engine?: string | null
}

export interface DevColumn {
  name: string
  data_type?: string
  column_type?: string
  nullable?: boolean
  key?: string
  sensitive?: boolean
}

export interface DevRowsResponse {
  table: string
  total: number
  limit: number
  offset: number
  primary_key: string[]
  columns: DevColumn[]
  rows: Record<string, unknown>[]
}

export interface DevAuditItem {
  id: number
  actor_username?: string | null
  action: string
  resource_type: string
  resource_id?: string | null
  table_name?: string | null
  before?: unknown
  after?: unknown
  created_at?: string | null
}

export interface DevFlag {
  flag_key: string
  enabled: boolean
  description?: string | null
  value?: unknown
}

export const developerApi = {
  overview: () => apiRequest<{ environment: string; destructive_confirm_phrase: string; panels: string[] }>('/api/developer/overview'),
  health: () => apiRequest<Record<string, unknown>>('/api/developer/health'),
  migrations: () => apiRequest<Record<string, unknown>>('/api/developer/migrations'),
  settings: () => apiRequest<Record<string, unknown>>('/api/developer/settings'),
  tables: () => apiRequest<{ tables: DevTableInfo[] }>('/api/developer/tables'),
  tableSchema: (table: string) => apiRequest<Record<string, unknown>>(`/api/developer/tables/${encodeURIComponent(table)}`),
  rows: (table: string, params: Record<string, string | number | boolean | undefined>) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== '') q.set(k, String(v))
    })
    return apiRequest<DevRowsResponse>(`/api/developer/tables/${encodeURIComponent(table)}/rows?${q}`)
  },
  createRow: (table: string, data: Record<string, unknown>) =>
    apiRequest(`/api/developer/tables/${encodeURIComponent(table)}/rows`, {
      method: 'POST',
      body: JSON.stringify({ data }),
    }),
  updateRow: (table: string, pk: Record<string, unknown>, data: Record<string, unknown>) =>
    apiRequest(`/api/developer/tables/${encodeURIComponent(table)}/rows`, {
      method: 'PUT',
      body: JSON.stringify({ pk, data }),
    }),
  deleteRow: (
    table: string,
    pk: Record<string, unknown>,
    confirm: { confirm: boolean; confirm_phrase: string; production_password?: string },
  ) =>
    apiRequest(`/api/developer/tables/${encodeURIComponent(table)}/rows/delete`, {
      method: 'POST',
      body: JSON.stringify({ pk, ...confirm }),
    }),
  bulkDelete: (
    table: string,
    pk_list: Record<string, unknown>[],
    confirm: { confirm: boolean; confirm_phrase: string; production_password?: string },
  ) =>
    apiRequest(`/api/developer/tables/${encodeURIComponent(table)}/rows/bulk-delete`, {
      method: 'POST',
      body: JSON.stringify({ pk_list, ...confirm }),
    }),
  bulkUpdate: (
    table: string,
    pk_list: Record<string, unknown>[],
    data: Record<string, unknown>,
    confirm: { confirm: boolean; confirm_phrase: string; production_password?: string },
  ) =>
    apiRequest(`/api/developer/tables/${encodeURIComponent(table)}/rows/bulk-update`, {
      method: 'POST',
      body: JSON.stringify({ pk_list, data, ...confirm }),
    }),
  audit: (params: Record<string, string | number | undefined> = {}) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== '') q.set(k, String(v))
    })
    return apiRequest<{ total: number; items: DevAuditItem[] }>(`/api/developer/audit?${q}`)
  },
  activity: (params: Record<string, string | number | undefined> = {}) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== '') q.set(k, String(v))
    })
    return apiRequest<{ total: number; items: DevAuditItem[] }>(`/api/developer/activity?${q}`)
  },
  sessions: () => apiRequest<{ sessions: Record<string, unknown>[] }>('/api/developer/sessions'),
  revokeSession: (sessionId: string) =>
    apiRequest(`/api/developer/sessions/${encodeURIComponent(sessionId)}/revoke`, { method: 'POST' }),
  userCredentials: (userId: number) =>
    apiRequest<Record<string, unknown>>(`/api/developer/users/${userId}/credentials`),
  apiLogs: (params: Record<string, string | number | boolean | undefined> = {}) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== '') q.set(k, String(v))
    })
    return apiRequest<{ total: number; items: Record<string, unknown>[] }>(`/api/developer/api-logs?${q}`)
  },
  errorLogs: () => apiRequest<{ total: number; items: Record<string, unknown>[] }>('/api/developer/error-logs'),
  flags: () => apiRequest<{ flags: DevFlag[] }>('/api/developer/feature-flags'),
  upsertFlag: (body: { flag_key: string; enabled: boolean; description?: string }) =>
    apiRequest('/api/developer/feature-flags', { method: 'PUT', body: JSON.stringify(body) }),
  clearApiLogs: (confirm: { confirm: boolean; confirm_phrase: string; production_password?: string }) =>
    apiRequest('/api/developer/cache/clear', {
      method: 'POST',
      body: JSON.stringify({ target: 'api_logs', ...confirm }),
    }),
  jobs: () => apiRequest<Record<string, unknown>>('/api/developer/jobs'),
  webhooks: () => apiRequest<Record<string, unknown>>('/api/developer/webhooks'),
}
