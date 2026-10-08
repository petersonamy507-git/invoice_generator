import { api, downloadBlob, unwrapList } from './client'
import type {
  ApiEmployee,
  ApiEmployeeCreate,
  ApiEmployeeUpdate,
  GenerateInvoicesRequest,
} from './types'

function asEmployee(data: unknown): ApiEmployee {
  if (data && typeof data === 'object' && 'employee' in data) {
    return (data as { employee: ApiEmployee }).employee
  }
  return data as ApiEmployee
}

export async function listEmployees(department?: string): Promise<ApiEmployee[]> {
  const query = department ? `?department=${encodeURIComponent(department)}` : ''
  const data = await api<unknown>(`/api/employees${query}`)
  return unwrapList<ApiEmployee>(data, ['employees', 'items', 'data', 'results'])
}

export async function createEmployee(payload: ApiEmployeeCreate) {
  const data = await api<unknown>('/api/employees', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return asEmployee(data)
}

export async function updateEmployee(employeeId: string, payload: ApiEmployeeUpdate) {
  const data = await api<unknown>(`/api/employees/${encodeURIComponent(employeeId)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  return asEmployee(data)
}

export function deleteEmployee(employeeId: string) {
  return api<unknown>(`/api/employees/${encodeURIComponent(employeeId)}`, {
    method: 'DELETE',
  })
}

export async function generateInvoices(payload: GenerateInvoicesRequest): Promise<void> {
  const blob = await api<Blob>('/api/employees/generate', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  downloadBlob(blob, `invoices-${new Date().toISOString().slice(0, 10)}.zip`)
}
