import { useState } from 'react'
import type { FormEvent } from 'react'
import { BANKS } from '../../data/catalog'
import type { Department, Employee, EmployeeDraft } from '../../types'
import { formatAmount, parseAmount } from '../../utils/format'
import { LayersIcon } from '../icons'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { SelectField } from '../ui/SelectField'
import { TextField } from '../ui/TextField'

interface EmployeeFormModalProps {
  mode: 'create' | 'edit'
  employee?: Employee | null
  departments: Department[]
  defaultDepartment: string
  onClose: () => void
  onSubmit: (draft: EmployeeDraft) => Promise<void>
}

interface FormState {
  id: string
  department: string
  invoiceNo: string
  accountTitle: string
  bank: string
  branchCode: string
  iban: string
  amount: string
}

function emptyForm(department: string): FormState {
  return {
    id: '',
    department,
    invoiceNo: '',
    accountTitle: '',
    bank: BANKS[0],
    branchCode: '',
    iban: '',
    amount: '',
  }
}

function fromEmployee(employee: Employee): FormState {
  return {
    id: employee.id,
    department: employee.department,
    invoiceNo: employee.invoiceNo,
    accountTitle: employee.accountTitle,
    bank: employee.bank,
    branchCode: employee.branchCode,
    iban: employee.iban,
    amount: employee.amount ? formatAmount(employee.amount) : '',
  }
}

export function EmployeeFormModal({
  mode,
  employee,
  departments,
  defaultDepartment,
  onClose,
  onSubmit,
}: EmployeeFormModalProps) {
  const [form, setForm] = useState<FormState>(() => (employee ? fromEmployee(employee) : emptyForm(defaultDepartment)))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const update = (patch: Partial<FormState>) => setForm((current) => ({ ...current, ...patch }))

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const amount = form.amount.trim() ? parseAmount(form.amount) : 0
    if (mode === 'create' && !form.id.trim()) {
      setError('Enter an employee ID (e.g. EMP001).')
      return
    }
    if (!form.accountTitle.trim()) {
      setError('Enter the employee full name / account title.')
      return
    }
    if (!form.branchCode.trim()) {
      setError('Enter the branch code.')
      return
    }
    if (form.iban.trim().length < 8) {
      setError('Enter a valid IBAN.')
      return
    }
    if (!Number.isFinite(amount) || amount < 0) {
      setError('Enter an amount of 0 or more.')
      return
    }

    setBusy(true)
    setError('')
    try {
      await onSubmit({
        id: form.id.trim(),
        department: form.department,
        bank: form.bank,
        accountTitle: form.accountTitle.trim(),
        iban: form.iban.trim(),
        branchCode: form.branchCode.trim(),
        invoiceNo: form.invoiceNo.trim(),
        amount,
      })
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save employee.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title={mode === 'create' ? 'Add New Employee Record' : 'Edit Employee Record'}
      subtitle={
        mode === 'create'
          ? 'Add a team member to the selected department payroll system.'
          : 'Update this payroll record before generating invoices.'
      }
      icon={<LayersIcon />}
      onClose={onClose}
    >
      <form className="employee-form" onSubmit={(event) => void submit(event)}>
        <div className="form-grid">
          <TextField
            label="Employee ID"
            value={form.id}
            placeholder="e.g. EMP001"
            disabled={mode === 'edit'}
            onChange={(event) => update({ id: event.target.value })}
          />
          <SelectField
            label="Department Category"
            value={form.department}
            disabled={mode === 'edit'}
            onChange={(event) => update({ department: event.target.value })}
            options={departments.map((department) => ({ value: department.apiName, label: department.badgeName }))}
          />
          <TextField
            label="Last Invoice No."
            value={form.invoiceNo}
            placeholder="e.g. HH-007"
            onChange={(event) => update({ invoiceNo: event.target.value })}
          />
          <TextField
            label="Employee Full Name / Account Title"
            value={form.accountTitle}
            placeholder="e.g. Syed Muhammad Ali Abbasi"
            onChange={(event) => update({ accountTitle: event.target.value })}
          />
          <SelectField
            label="Bank Name"
            value={form.bank}
            onChange={(event) => update({ bank: event.target.value })}
            options={BANKS.map((bank) => ({ value: bank, label: bank }))}
          />
          <TextField
            label="Branch Code"
            value={form.branchCode}
            placeholder="7861"
            onChange={(event) => update({ branchCode: event.target.value })}
          />
          <TextField
            className="span-2"
            label="IBAN NO."
            value={form.iban}
            placeholder="e.g. PK36 SCBL 0000 0011 2345 6702"
            onChange={(event) => update({ iban: event.target.value })}
          />
          <TextField
            label="Amount (PKR)"
            prefix="PKR"
            inputMode="decimal"
            value={form.amount}
            placeholder="180,000"
            onChange={(event) => update({ amount: event.target.value })}
          />
        </div>
        {error ? <p className="form-error">{error}</p> : null}
        <div className="modal-actions">
          <Button variant="secondary" type="button" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy}>
            {busy ? 'Saving...' : mode === 'create' ? 'Save & Add Employee' : 'Save Changes'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
