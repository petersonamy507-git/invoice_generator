import { api } from './client'
import { INVOICE_TEMPLATES, type InvoiceTemplateOption } from '../data/templates'

export interface ApiTemplateInfo {
  id: number
  label: string
  name?: string
  filename?: string
  exists?: boolean
}

export interface TemplatesStatusResponse {
  templates?: Record<string, ApiTemplateInfo>
  word_dir?: string
  preview_dir?: string
}

export function getTemplatesStatus() {
  return api<TemplatesStatusResponse>('/api/templates/status')
}

export async function listInvoiceTemplates(): Promise<InvoiceTemplateOption[]> {
  try {
    const data = await getTemplatesStatus()
    const rows = Object.values(data.templates ?? {})
      .filter((row) => row && typeof row.id === 'number')
      .map((row) => ({
        id: row.id,
        label: row.label || `Template ${row.id}`,
        name: row.name,
        exists: row.exists,
      }))
      .sort((a, b) => a.id - b.id)

    return rows.length > 0 ? rows : INVOICE_TEMPLATES
  } catch {
    return INVOICE_TEMPLATES
  }
}
