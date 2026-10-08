import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ApiError } from '../api/client'
import { listDepartments } from '../api/departments'
import * as employeesApi from '../api/employees'
import { listInvoiceTemplates } from '../api/templates'
import { departmentByApiName, departmentsFromApi } from '../data/catalog'
import { INVOICE_TEMPLATES, type InvoiceTemplateOption } from '../data/templates'
import type { Department, Employee, EmployeeDraft } from '../types'
import { mapApiEmployee } from '../types'
import { useAuth } from './AuthContext'

interface PayrollContextValue {
  departments: Department[]
  departmentId: string
  setDepartmentId: (id: string) => void
  employees: Employee[]
  templates: InvoiceTemplateOption[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  addEmployee: (draft: EmployeeDraft) => Promise<void>
  updateEmployee: (id: string, draft: EmployeeDraft) => Promise<void>
  patchEmployee: (id: string, patch: Partial<Employee>) => void
  removeEmployee: (id: string) => Promise<void>
  toggleSelected: (id: string) => void
  setSelected: (ids: string[], selected: boolean) => void
  generateSelected: (selected: Employee[]) => Promise<void>
}

const PayrollContext = createContext<PayrollContextValue | null>(null)

export function PayrollProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const [departments, setDepartments] = useState<Department[]>(() => departmentsFromApi([]))
  const [departmentId, setDepartmentId] = useState('')
  const [employees, setEmployees] = useState<Employee[]>([])
  const [templates, setTemplates] = useState<InvoiceTemplateOption[]>(INVOICE_TEMPLATES)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!user) {
      setEmployees([])
      setError(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [deptNames, employeeRows, templateRows] = await Promise.all([
        listDepartments(),
        employeesApi.listEmployees(),
        listInvoiceTemplates(),
      ])
      const nextDepartments = departmentsFromApi(deptNames)
      setDepartments(nextDepartments)
      setTemplates(templateRows)
      setDepartmentId((current) => {
        if (current && nextDepartments.some((item) => item.id === current)) return current
        return nextDepartments[0]?.id ?? ''
      })
      setEmployees((previous) =>
        employeeRows.map((row) => {
          const prev = previous.find((item) => item.id === row.employee_id)
          return mapApiEmployee(row, prev)
        }),
      )
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.status === 401
            ? 'Session expired. Please sign in again.'
            : err.detail || err.message
          : 'Unable to load payroll data from the API.'
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const value = useMemo<PayrollContextValue>(
    () => ({
      departments,
      departmentId,
      setDepartmentId,
      employees,
      templates,
      loading,
      error,
      refresh,
      addEmployee: async (draft) => {
        const employeeId = draft.id?.trim()
        if (!employeeId) throw new Error('Employee ID is required.')
        const created = await employeesApi.createEmployee({
          employee_id: employeeId,
          name: draft.accountTitle.trim(),
          department: draft.department,
          iban: draft.iban.trim(),
          bank_name: draft.bank.trim(),
          branch_code: draft.branchCode.trim(),
          last_invoice: draft.invoiceNo.trim() || undefined,
        })
        const department = departmentByApiName(departments, draft.department)
        setDepartmentId(department.id)
        setEmployees((current) => {
          const mapped = mapApiEmployee(created, {
            id: employeeId,
            department: draft.department,
            bank: draft.bank,
            accountTitle: draft.accountTitle,
            iban: draft.iban,
            branchCode: draft.branchCode,
            invoiceNo: draft.invoiceNo,
            amount: draft.amount,
            selected: false,
            invoiceTemplate: draft.invoiceTemplate ?? 1,
          })
          return [mapped, ...current.filter((item) => item.id !== employeeId)]
        })
      },
      updateEmployee: async (id, draft) => {
        const updated = await employeesApi.updateEmployee(id, {
          name: draft.accountTitle.trim(),
          iban: draft.iban.trim(),
          bank_name: draft.bank.trim(),
          branch_code: draft.branchCode.trim(),
          last_invoice: draft.invoiceNo.trim() || undefined,
        })
        setEmployees((current) =>
          current.map((employee) =>
            employee.id === id
              ? mapApiEmployee(updated, {
                  ...employee,
                  amount: draft.amount,
                  invoiceTemplate: draft.invoiceTemplate ?? employee.invoiceTemplate,
                })
              : employee,
          ),
        )
      },
      patchEmployee: (id, patch) => {
        setEmployees((current) => current.map((employee) => (employee.id === id ? { ...employee, ...patch } : employee)))
      },
      removeEmployee: async (id) => {
        await employeesApi.deleteEmployee(id)
        setEmployees((current) => current.filter((employee) => employee.id !== id))
      },
      toggleSelected: (id) => {
        setEmployees((current) =>
          current.map((employee) => (employee.id === id ? { ...employee, selected: !employee.selected } : employee)),
        )
      },
      setSelected: (ids, selected) => {
        const idSet = new Set(ids)
        setEmployees((current) =>
          current.map((employee) => (idSet.has(employee.id) ? { ...employee, selected } : employee)),
        )
      },
      generateSelected: async (selected) => {
        await employeesApi.generateInvoices({
          employees: selected.map((employee) => ({
            employee_id: employee.id,
            amount: employee.amount,
            invoice_no: employee.invoiceNo.trim(),
            invoice_template: employee.invoiceTemplate || 1,
          })),
        })
        await refresh()
      },
    }),
    [departments, departmentId, employees, templates, loading, error, refresh],
  )

  return <PayrollContext.Provider value={value}>{children}</PayrollContext.Provider>
}

export function usePayroll(): PayrollContextValue {
  const context = useContext(PayrollContext)
  if (!context) throw new Error('usePayroll must be used within PayrollProvider')
  return context
}
