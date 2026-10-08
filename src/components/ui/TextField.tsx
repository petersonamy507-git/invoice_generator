import type { InputHTMLAttributes, ReactNode } from 'react'

type TextFieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string
  icon?: ReactNode
  prefix?: string
}

export function TextField({ label, icon, prefix, id, className = '', ...props }: TextFieldProps) {
  const fieldId = id ?? label.toLowerCase().replace(/[^a-z0-9]+/g, '-')
  return (
    <label className={`field ${className}`} htmlFor={fieldId}>
      <span className="field-label">{label}</span>
      <span className="field-control">
        {icon ? <span className="field-icon">{icon}</span> : null}
        {prefix ? <span className="field-prefix">{prefix}</span> : null}
        <input id={fieldId} {...props} />
      </span>
    </label>
  )
}
