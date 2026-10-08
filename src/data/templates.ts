export type InvoiceTemplateOption = {
  id: number
  label: string
  name?: string
  exists?: boolean
}

/** Fallback labels when `/api/templates/status` is unavailable. */
export const INVOICE_TEMPLATES: InvoiceTemplateOption[] = [
  { id: 1, label: 'MAXIS' },
  { id: 2, label: 'Forest Tech' },
  { id: 3, label: 'Radnor Innovations' },
  { id: 4, label: 'App Founders' },
  { id: 5, label: 'Dynamo Creatives' },
  { id: 6, label: 'Ravotek' },
  { id: 7, label: 'Ignitai' },
  { id: 8, label: 'Coretechify' },
  { id: 9, label: 'Ecomify' },
  { id: 10, label: 'Cozy Home Essentials' },
  { id: 11, label: 'Beecodify' },
  { id: 12, label: 'Bravix Technologies' },
  { id: 13, label: 'Alpha Digital' },
  { id: 14, label: 'Synergo' },
]

export function templateLabel(templates: InvoiceTemplateOption[], id: number): string {
  return templates.find((item) => item.id === id)?.label ?? `Template ${id}`
}
