import { useMemo, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { DepartmentCard } from '../components/invoice/DepartmentCard'
import { EmployeeFormModal } from '../components/invoice/EmployeeFormModal'
import { EmployeeTable } from '../components/invoice/EmployeeTable'
import { DownloadIcon, PlusIcon, SearchIcon } from '../components/icons'
import { AppHeader } from '../components/layout/AppChrome'
import { Button } from '../components/ui/Button'
import { Toast, useToast } from '../components/ui/Toast'
import { departmentById } from '../data/catalog'
import { useAuth } from '../context/AuthContext'
import { usePayroll } from '../context/PayrollContext'
import type { Employee, EmployeeDraft } from '../types'
import { formatPkr } from '../utils/format'

export function InvoicePage() {
  const { user, bootstrapping, signOut } = useAuth()
  const payroll = usePayroll()
  const notify = useToast()
  const [query, setQuery] = useState('')
  const [editor, setEditor] = useState<Employee | null | 'create'>(null)
  const [busy, setBusy] = useState(false)

  const department = departmentById(payroll.departments, payroll.departmentId)
  const counts = useMemo(() => {
    return Object.fromEntries(
      payroll.departments.map((item) => [
        item.id,
        payroll.employees.filter((employee) => employee.department === item.apiName).length,
      ]),
    )
  }, [payroll.departments, payroll.employees])

  const visible = useMemo(() => {
    const term = query.trim().toLowerCase()
    return payroll.employees.filter((employee) => {
      if (department && employee.department !== department.apiName) return false
      if (!term) return true
      return [employee.id, employee.bank, employee.accountTitle, employee.iban, employee.branchCode, employee.invoiceNo, String(employee.amount)]
        .join(' ')
        .toLowerCase()
        .includes(term)
    })
  }, [department, payroll.employees, query])

  const selected = visible.filter((employee) => employee.selected)
  const total = selected.reduce((sum, employee) => sum + employee.amount, 0)

  if (bootstrapping) {
    return (
      <div className="app-shell">
        <main className="page">
          <p className="empty-state">Loading session...</p>
        </main>
        <Toast message="Loading session..." tone="loading" />
      </div>
    )
  }

  if (!user) return <Navigate to="/signin" replace />

  const saveEmployee = async (draft: EmployeeDraft) => {
    notify.showLoading('Saving employee...')
    try {
      if (editor && editor !== 'create') await payroll.updateEmployee(editor.id, draft)
      else await payroll.addEmployee(draft)
      notify.showSuccess(editor && editor !== 'create' ? 'Employee updated.' : 'Employee added.')
    } catch (error) {
      notify.showError(error instanceof ApiError ? error.detail || error.message : 'Unable to save employee.')
      throw error
    }
  }

  const removeEmployee = async (id: string) => {
    notify.showLoading('Removing employee...')
    try {
      await payroll.removeEmployee(id)
      notify.showSuccess('Employee removed.')
    } catch (error) {
      notify.showError(error instanceof ApiError ? error.detail || error.message : 'Unable to remove employee.')
    }
  }

  const generate = async () => {
    if (selected.length === 0 || busy) return
    const missing = selected.find((employee) => !employee.invoiceNo.trim() || employee.amount <= 0)
    if (missing) {
      notify.showError('Selected employees need an invoice number and amount greater than 0.')
      return
    }
    setBusy(true)
    notify.showLoading('Preparing invoice ZIP...')
    try {
      await payroll.generateSelected(selected)
      notify.showSuccess(`${selected.length} invoice${selected.length === 1 ? '' : 's'} downloaded.`)
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        notify.showError('Session expired. Please sign in again.')
        await signOut()
      } else {
        notify.showError(
          error instanceof ApiError
            ? error.detail || error.message
            : error instanceof Error
              ? error.message
              : 'The bundle could not be created.',
        )
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app-shell">
      <AppHeader />
      <main className="page page-workspace">
        <header className="workspace-hero reveal">
          <div className="workspace-hero-copy">
            <p className="page-kicker">Payroll invoices</p>
            <h1>Build this week’s ZIP</h1>
            <p>
              Filter a team, select people, fill invoice + amount + template, then download PDFs in one click.
            </p>
          </div>
          <div className="workspace-metrics" aria-label="Selection summary">
            <div className="metric">
              <span className="metric-label">Showing</span>
              <strong>{visible.length}</strong>
            </div>
            <div className="metric">
              <span className="metric-label">Selected</span>
              <strong className={selected.length ? 'is-accent' : ''}>{selected.length}</strong>
            </div>
            <div className="metric metric-wide">
              <span className="metric-label">Bundle total</span>
              <strong className="sum">{formatPkr(total)}</strong>
            </div>
          </div>
        </header>

        {payroll.error ? (
          <div className="banner-error">
            <span>{payroll.error}</span>
            <Button variant="secondary" onClick={() => void payroll.refresh()}>
              Retry
            </Button>
          </div>
        ) : null}

        <section className="workspace-filters reveal" aria-label="Departments">
          <div className="workspace-filters-head">
            <h2>Team</h2>
            <p>Jump to a department to narrow the list.</p>
          </div>
          <div className="dept-chip-row" role="listbox" aria-label="Department filter">
            {payroll.departments.map((item) => (
              <DepartmentCard
                key={item.id}
                department={item}
                count={counts[item.id] ?? 0}
                active={item.id === payroll.departmentId}
                onSelect={() => {
                  payroll.setDepartmentId(item.id)
                  setQuery('')
                }}
              />
            ))}
          </div>
        </section>

        <section className="workspace-panel reveal">
          <header className="workspace-panel-head">
            <div>
              <h2>{department?.name ?? 'Employees'}</h2>
              <p>
                {selected.length > 0
                  ? `${selected.length} selected · edit invoice fields on selected rows`
                  : 'Select rows to enter invoice number, amount, and template'}
              </p>
            </div>
            <div className="list-tools">
              <label className="search-field">
                <SearchIcon />
                <input
                  value={query}
                  placeholder="Search name, ID, invoice..."
                  onChange={(event) => setQuery(event.target.value)}
                  aria-label="Search employees"
                />
              </label>
              {user.isAdmin ? (
                <Button className="add-employee-btn" icon={<PlusIcon />} onClick={() => setEditor('create')}>
                  <span className="label-full">Add employee</span>
                  <span className="label-short">Add</span>
                </Button>
              ) : null}
            </div>
          </header>

          {payroll.loading ? <p className="empty-state">Loading employees...</p> : null}
          {!payroll.loading ? (
            <EmployeeTable
              employees={visible}
              templates={payroll.templates}
              canManage={user.isAdmin}
              onToggle={payroll.toggleSelected}
              onToggleAll={(checked) => payroll.setSelected(visible.map((employee) => employee.id), checked)}
              onInvoiceChange={(id, invoiceNo) => payroll.patchEmployee(id, { invoiceNo })}
              onAmountChange={(id, amount) => payroll.patchEmployee(id, { amount })}
              onTemplateChange={(id, invoiceTemplate) => payroll.patchEmployee(id, { invoiceTemplate })}
              onEdit={setEditor}
              onRemove={(id) => void removeEmployee(id)}
            />
          ) : null}
        </section>
      </main>

      <div className={`action-dock ${selected.length ? 'is-ready' : ''}`}>
        <div className="action-dock-inner">
          <div className="action-dock-copy">
            <strong>
              {selected.length === 0
                ? 'Select people to generate'
                : `${selected.length} ready · ${formatPkr(total)}`}
            </strong>
            <span>
              {selected.length === 0
                ? 'Tip: check a row, then fill Last Invoice, Amount, and Template.'
                : 'Confirm invoice numbers and amounts before downloading.'}
            </span>
          </div>
          <Button
            className="generate-btn"
            icon={<DownloadIcon />}
            disabled={selected.length === 0 || busy || payroll.loading}
            onClick={() => void generate()}
          >
            <span className="label-full">{busy ? 'Preparing ZIP...' : 'Download PDF ZIP'}</span>
            <span className="label-short">{busy ? 'Preparing...' : 'Download ZIP'}</span>
          </Button>
        </div>
      </div>

      {editor && user.isAdmin ? (
        <EmployeeFormModal
          key={editor === 'create' ? 'create' : editor.id}
          mode={editor === 'create' ? 'create' : 'edit'}
          employee={editor === 'create' ? null : editor}
          departments={payroll.departments}
          defaultDepartment={department?.apiName ?? payroll.departments[0]?.apiName ?? 'QA'}
          onClose={() => setEditor(null)}
          onSubmit={saveEmployee}
        />
      ) : null}
      {payroll.loading && !notify.toast.message ? (
        <Toast message="Loading employees..." tone="loading" />
      ) : (
        <Toast message={notify.toast.message} tone={notify.toast.tone} onClose={notify.clear} />
      )}
    </div>
  )
}
