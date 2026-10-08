import type { SelectHTMLAttributes } from 'react'
import { ChevronIcon } from '../icons'

type Option = {
  value: string
  label: string
}

type SelectFieldProps = SelectHTMLAttributes<HTMLSelectElement> & {
  label: string
  options: Option[]
}

export function SelectField({ label, options, id, className = '', ...props }: SelectFieldProps) {
  const fieldId = id ?? label.toLowerCase().replace(/[^a-z0-9]+/g, '-')
  return (
    <label className={`field ${className}`} htmlFor={fieldId}>
      <span className="field-label">{label}</span>
      <span className="field-control field-select">
        <select id={fieldId} {...props}>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <ChevronIcon className="select-chevron" />
      </span>
    </label>
  )
}
