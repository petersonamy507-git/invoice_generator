import { forwardRef } from 'react'
import type { InputHTMLAttributes } from 'react'
import { CheckIcon } from '../icons'

type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & {
  label?: string
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { label, className = '', ...props },
  ref,
) {
  return (
    <label className={`checkbox ${className}`}>
      <input ref={ref} type="checkbox" {...props} />
      <span className="checkbox-box" aria-hidden="true">
        <CheckIcon />
      </span>
      {label ? <span>{label}</span> : null}
    </label>
  )
})
