import { useState, type InputHTMLAttributes, type ReactNode } from 'react'
import { EyeIcon, EyeOffIcon } from '../icons'

type TextFieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string
  icon?: ReactNode
  prefix?: string
  /** Show eye toggle for password fields (default true when type="password"). */
  showPasswordToggle?: boolean
  /** Start with password visible (still toggleable). */
  defaultPasswordVisible?: boolean
}

export function TextField({
  label,
  icon,
  prefix,
  id,
  className = '',
  type = 'text',
  showPasswordToggle,
  defaultPasswordVisible = false,
  ...props
}: TextFieldProps) {
  const fieldId = id ?? label.toLowerCase().replace(/[^a-z0-9]+/g, '-')
  const isPassword = type === 'password'
  const canReveal = isPassword && showPasswordToggle !== false
  const [visible, setVisible] = useState(defaultPasswordVisible)
  const inputType = canReveal && visible ? 'text' : type

  return (
    <label className={`field ${className}`} htmlFor={fieldId}>
      <span className="field-label">{label}</span>
      <span className={`field-control${canReveal ? ' has-reveal' : ''}`}>
        {icon ? <span className="field-icon">{icon}</span> : null}
        {prefix ? <span className="field-prefix">{prefix}</span> : null}
        <input id={fieldId} {...props} type={inputType} />
        {canReveal ? (
          <button
            type="button"
            className="field-reveal"
            onClick={(e) => {
              e.preventDefault()
              setVisible((v) => !v)
            }}
            aria-label={visible ? 'Hide password' : 'Show password'}
            title={visible ? 'Hide password' : 'Show password'}
          >
            {visible ? <EyeOffIcon /> : <EyeIcon />}
          </button>
        ) : null}
      </span>
    </label>
  )
}
