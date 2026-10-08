import { useEffect, useRef, useState } from 'react'
import { INVOICE_TEMPLATES, templateLabel, type InvoiceTemplateOption } from '../../data/templates'
import type { Employee } from '../../types'
import { formatAmount, formatPkr, parseAmount } from '../../utils/format'
import { Checkbox } from '../ui/Checkbox'
import { RowMenu } from './RowMenu'

interface EmployeeTableProps {
  employees: Employee[]
  templates?: InvoiceTemplateOption[]
  canManage?: boolean
  onToggle: (id: string) => void
  onToggleAll: (selected: boolean) => void
  onInvoiceChange: (id: string, invoiceNo: string) => void
  onAmountChange: (id: string, amount: number) => void
  onTemplateChange: (id: string, invoiceTemplate: number) => void
  onEdit: (employee: Employee) => void
  onRemove: (id: string) => void
}

export function EmployeeTable({
  employees,
  templates = INVOICE_TEMPLATES,
  canManage = false,
  onToggle,
  onToggleAll,
  onInvoiceChange,
  onAmountChange,
  onTemplateChange,
  onEdit,
  onRemove,
}: EmployeeTableProps) {
  const allSelected = employees.length > 0 && employees.every((employee) => employee.selected)
  const someSelected = employees.some((employee) => employee.selected)
  const headerRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (headerRef.current) headerRef.current.indeterminate = someSelected && !allSelected
  }, [someSelected, allSelected])

  if (employees.length === 0) {
    return <p className="empty-state">No employees match this department or search.</p>
  }

  return (
    <>
      <div className="employee-mobile-toolbar">
        <Checkbox
          checked={allSelected}
          onChange={(event) => onToggleAll(event.target.checked)}
          aria-label="Select all employees"
          label={allSelected ? 'Deselect all' : 'Select all'}
        />
        <span>{employees.length} record{employees.length === 1 ? '' : 's'}</span>
      </div>

      <div className="employee-cards">
        {employees.map((employee) => (
          <article key={employee.id} className={`employee-card ${employee.selected ? 'is-selected' : ''}`}>
            <header className="employee-card-top">
              <Checkbox
                checked={employee.selected}
                onChange={() => onToggle(employee.id)}
                aria-label={`Select ${employee.accountTitle}`}
              />
              <div className="employee-card-title">
                <strong>{employee.accountTitle}</strong>
                <span>{employee.bank}</span>
              </div>
              {canManage ? (
                <RowMenu onEdit={() => onEdit(employee)} onRemove={() => onRemove(employee.id)} />
              ) : null}
            </header>

            <dl className="employee-card-meta">
              <div>
                <dt>Employee ID</dt>
                <dd>{employee.id}</dd>
              </div>
              <div>
                <dt>IBAN</dt>
                <dd className="mono">{employee.iban}</dd>
              </div>
              <div>
                <dt>Branch</dt>
                <dd>{employee.branchCode}</dd>
              </div>
              {!employee.selected ? (
                <>
                  <div>
                    <dt>Last Invoice</dt>
                    <dd>{employee.invoiceNo || '—'}</dd>
                  </div>
                  <div>
                    <dt>Amount</dt>
                    <dd>{formatPkr(employee.amount)}</dd>
                  </div>
                </>
              ) : null}
            </dl>

            {employee.selected ? (
              <div className="employee-card-fields">
                <label className="field">
                  <span className="field-label">Last Invoice No.</span>
                  <span className="field-control">
                    <input
                      aria-label={`Invoice number for ${employee.accountTitle}`}
                      value={employee.invoiceNo}
                      placeholder="HH-007"
                      onChange={(event) => onInvoiceChange(employee.id, event.target.value)}
                    />
                  </span>
                </label>
                <label className="field">
                  <span className="field-label">Amount</span>
                  <span className="field-control">
                    <span className="field-prefix">PKR</span>
                    <AmountInput
                      key={`${employee.id}-${employee.amount}`}
                      value={employee.amount}
                      label={`Amount for ${employee.accountTitle}`}
                      onCommit={(amount) => onAmountChange(employee.id, amount)}
                    />
                  </span>
                </label>
                <label className="field">
                  <span className="field-label">Invoice template</span>
                  <span className="field-control field-select">
                    <select
                      aria-label={`Invoice template for ${employee.accountTitle}`}
                      value={employee.invoiceTemplate}
                      onChange={(event) => onTemplateChange(employee.id, Number(event.target.value))}
                    >
                      {templates.map((template) => (
                        <option key={template.id} value={template.id}>
                          {template.label}
                        </option>
                      ))}
                    </select>
                  </span>
                </label>
              </div>
            ) : null}
          </article>
        ))}
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th className="col-check">
                <Checkbox
                  ref={headerRef}
                  checked={allSelected}
                  onChange={(event) => onToggleAll(event.target.checked)}
                  aria-label="Select all employees"
                />
              </th>
              <th>ID</th>
              <th>Bank</th>
              <th>Account Title</th>
              <th>IBAN NO.</th>
              <th>Branch code</th>
              <th>Last Invoice</th>
              <th>Amount (PKR)</th>
              <th>Template</th>
              {canManage ? <th className="col-action">Action</th> : null}
            </tr>
          </thead>
          <tbody>
            {employees.map((employee) => (
              <tr key={employee.id} className={employee.selected ? 'is-selected' : ''}>
                <td>
                  <Checkbox
                    checked={employee.selected}
                    onChange={() => onToggle(employee.id)}
                    aria-label={`Select ${employee.accountTitle}`}
                  />
                </td>
                <td className="mono">{employee.id}</td>
                <td>{employee.bank}</td>
                <td>{employee.accountTitle}</td>
                <td className="mono">{employee.iban}</td>
                <td>{employee.branchCode}</td>
                <td>
                  {employee.selected ? (
                    <input
                      className="cell-input"
                      aria-label={`Invoice number for ${employee.accountTitle}`}
                      value={employee.invoiceNo}
                      placeholder="HH-007"
                      onChange={(event) => onInvoiceChange(employee.id, event.target.value)}
                    />
                  ) : (
                    <span className="cell-value">{employee.invoiceNo || '—'}</span>
                  )}
                </td>
                <td>
                  {employee.selected ? (
                    <AmountCell
                      key={`${employee.id}-${employee.amount}`}
                      value={employee.amount}
                      label={`Amount for ${employee.accountTitle}`}
                      onCommit={(amount) => onAmountChange(employee.id, amount)}
                    />
                  ) : (
                    <span className="cell-value cell-amount">{formatPkr(employee.amount)}</span>
                  )}
                </td>
                <td>
                  {employee.selected ? (
                    <select
                      className="cell-select cell-select-template"
                      aria-label={`Invoice template for ${employee.accountTitle}`}
                      value={employee.invoiceTemplate}
                      onChange={(event) => onTemplateChange(employee.id, Number(event.target.value))}
                    >
                      {templates.map((template) => (
                        <option key={template.id} value={template.id}>
                          {template.label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="cell-value">{templateLabel(templates, employee.invoiceTemplate)}</span>
                  )}
                </td>
                {canManage ? (
                  <td className="col-action">
                    <RowMenu onEdit={() => onEdit(employee)} onRemove={() => onRemove(employee.id)} />
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function AmountCell({
  value,
  label,
  onCommit,
}: {
  value: number
  label: string
  onCommit: (amount: number) => void
}) {
  return (
    <label className="amount-cell">
      <span>PKR</span>
      <AmountInput value={value} label={label} onCommit={onCommit} />
    </label>
  )
}

function AmountInput({
  value,
  label,
  onCommit,
}: {
  value: number
  label: string
  onCommit: (amount: number) => void
}) {
  const formatted = formatAmount(value)
  const [draft, setDraft] = useState(value === 0 ? '' : formatted)

  return (
    <input
      aria-label={label}
      inputMode="decimal"
      value={draft}
      placeholder="0.00"
      onChange={(event) => setDraft(event.target.value)}
      onBlur={() => {
        if (!draft.trim()) {
          onCommit(0)
          setDraft('')
          return
        }
        const next = parseAmount(draft)
        if (!Number.isFinite(next) || next < 0) {
          setDraft(value === 0 ? '' : formatted)
          return
        }
        onCommit(next)
        setDraft(formatAmount(next))
      }}
    />
  )
}
