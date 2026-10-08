import type { Department } from '../types'

const DISPLAY: Record<string, { name: string; badgeName: string }> = {
  qa: { name: 'Quality assurance (QA)', badgeName: 'Quality Assurance (QA)' },
  devops: { name: 'DevOps', badgeName: 'DevOps' },
  'call centre': { name: 'Call Center', badgeName: 'Call Center' },
  'call center': { name: 'Call Center', badgeName: 'Call Center' },
  account: { name: 'Account', badgeName: 'Account' },
  hr: { name: 'Human Resource (HR)', badgeName: 'Human Resource (HR)' },
}

export const BANKS = [
  'United Bank Limited',
  'Habib Bank Limited (HBL)',
  'Bank Alfalah Limited',
  'Bank AL Habib Limited',
  'Meezan Bank Limited',
  'HBL',
  'UBL',
  'Meezan Bank',
] as const

export const FALLBACK_DEPARTMENTS = ['QA', 'Devops', 'Call centre', 'Account', 'HR']

export function slugifyDepartment(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'department'
}

export function toDepartment(apiName: string): Department {
  const key = apiName.trim().toLowerCase()
  const display = DISPLAY[key] ?? { name: apiName, badgeName: apiName }
  return {
    id: slugifyDepartment(apiName),
    name: display.name,
    badgeName: display.badgeName,
    apiName,
  }
}

export function departmentsFromApi(names: string[]): Department[] {
  const source = names.length > 0 ? names : FALLBACK_DEPARTMENTS
  return source.map(toDepartment)
}

export function departmentByApiName(departments: Department[], apiName: string): Department {
  return departments.find((item) => item.apiName === apiName) ?? toDepartment(apiName)
}

export function departmentById(departments: Department[], id: string): Department {
  return departments.find((item) => item.id === id) ?? departments[0] ?? toDepartment(id)
}
