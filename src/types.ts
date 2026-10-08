import type { ApiEmployee, ApiUser, UserRole } from './api/types'

export interface Department {
  id: string
  name: string
  badgeName: string
  apiName: string
}

export interface Employee {
  id: string
  department: string
  bank: string
  accountTitle: string
  iban: string
  branchCode: string
  invoiceNo: string
  amount: number
  selected: boolean
  invoiceTemplate: number
}

export interface EmployeeDraft {
  id?: string
  department: string
  bank: string
  accountTitle: string
  iban: string
  branchCode: string
  invoiceNo: string
  amount: number
  invoiceTemplate?: number
}

export interface SessionUser {
  id: number
  name: string
  email: string
  role: UserRole
  roleLabel: string
  username: string
  isAdmin: boolean
}

export function mapApiUser(user: ApiUser): SessionUser {
  const role: UserRole = user.role === 'admin' ? 'admin' : 'user'
  return {
    id: user.id,
    name: user.username,
    username: user.username,
    email: user.email,
    role,
    roleLabel: role === 'admin' ? 'Admin' : 'User',
    isAdmin: role === 'admin',
  }
}

export function mapApiEmployee(row: ApiEmployee, previous?: Employee): Employee {
  return {
    id: row.employee_id,
    department: row.department,
    bank: row.bank_name,
    accountTitle: row.name,
    iban: row.iban,
    branchCode: row.branch_code,
    invoiceNo: row.last_invoice?.trim() || previous?.invoiceNo || '',
    amount: previous?.amount ?? 0,
    selected: previous?.selected ?? false,
    invoiceTemplate: previous?.invoiceTemplate ?? 1,
  }
}
