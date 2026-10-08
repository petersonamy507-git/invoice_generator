export function formatAmount(value: number): string {
  if (value === 0) return '0.00'
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value)
}

export function formatPkr(value: number): string {
  return `PKR ${formatAmount(value)}`
}

export function parseAmount(raw: string): number {
  const normalized = raw.replace(/,/g, '').replace(/[^\d.]/g, '')
  if (!normalized) return Number.NaN
  const value = Number(normalized)
  return Number.isFinite(value) ? value : Number.NaN
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return 'U'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase()
}

export function fileSlug(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'invoice'
}
