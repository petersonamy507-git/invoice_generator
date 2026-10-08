export type UserRole = 'admin' | 'user'

export interface ApiUser {
  id: number
  username: string
  email: string
  role: UserRole | string
  is_active: boolean
  last_login?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface UserCreate {
  username: string
  email: string
  password: string
  confirm_password: string
  role?: UserRole
  is_active?: boolean
}

export interface UserUpdate {
  username?: string
  email?: string
  role?: UserRole
  is_active?: boolean
}

export interface UserPasswordUpdate {
  password: string
  confirm_password: string
}

export interface ApiEmployee {
  employee_id: string
  name: string
  department: string
  iban: string
  bank_name: string
  branch_code: string
  last_invoice?: string | null
  club_id?: string | number | null
}

export interface ApiEmployeeCreate {
  employee_id: string
  name: string
  department: string
  iban: string
  bank_name: string
  branch_code: string
  last_invoice?: string
}

export interface ApiEmployeeUpdate {
  name: string
  iban: string
  bank_name: string
  branch_code: string
  last_invoice?: string
}

export interface GenerateEmployeePayload {
  employee_id: string
  amount: number
  invoice_no: string
  invoice_template: number
}

export interface GenerateInvoicesRequest {
  employees: GenerateEmployeePayload[]
}
