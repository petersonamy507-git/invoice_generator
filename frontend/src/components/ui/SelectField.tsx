import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ChangeEvent,
  type CSSProperties,
  type KeyboardEvent,
  type SelectHTMLAttributes,
} from 'react'
import { createPortal } from 'react-dom'
import { ChevronIcon } from '../icons'

type Option = {
  value: string
  label: string
}

type SelectFieldProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, 'children'> & {
  label: string
  options: Option[]
}

/**
 * Custom select — native OS dropdowns misalign / wrong width on Windows.
 * Keeps the same value/onChange API as a native <select>.
 */
export function SelectField({
  label,
  options,
  id,
  className = '',
  value,
  disabled,
  onChange,
  name,
  required,
  ...rest
}: SelectFieldProps) {
  const reactId = useId()
  const fieldId = id ?? `select-${reactId}`
  const listId = `${fieldId}-listbox`
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({})

  const current = String(value ?? '')
  const selected = options.find((o) => o.value === current) ?? options[0]
  const selectedLabel = selected?.label ?? ''

  const placeMenu = () => {
    const el = triggerRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const gap = 6
    const spaceBelow = window.innerHeight - rect.bottom - gap
    const openUp = spaceBelow < 160 && rect.top > spaceBelow
    setMenuStyle({
      position: 'fixed',
      left: rect.left,
      width: rect.width,
      top: openUp ? undefined : rect.bottom + gap,
      bottom: openUp ? window.innerHeight - rect.top + gap : undefined,
      zIndex: 80,
    })
  }

  useLayoutEffect(() => {
    if (!open) return
    placeMenu()
  }, [open])

  useEffect(() => {
    if (!open) return
    const onDoc = (event: MouseEvent) => {
      const t = event.target as Node
      if (rootRef.current?.contains(t)) return
      if ((event.target as HTMLElement)?.closest?.(`#${CSS.escape(listId)}`)) return
      setOpen(false)
    }
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    const onReposition = () => placeMenu()
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    window.addEventListener('resize', onReposition)
    window.addEventListener('scroll', onReposition, true)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', onReposition)
      window.removeEventListener('scroll', onReposition, true)
    }
  }, [open, listId])

  const emit = (next: string) => {
    if (!onChange) return
    const event = {
      target: { value: next, name: name ?? fieldId },
      currentTarget: { value: next, name: name ?? fieldId },
    } as unknown as ChangeEvent<HTMLSelectElement>
    onChange(event)
  }

  const pick = (next: string) => {
    emit(next)
    setOpen(false)
  }

  const onTriggerKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return
    if (event.key === 'Enter' || event.key === ' ' || event.key === 'ArrowDown') {
      event.preventDefault()
      setOpen(true)
    }
  }

  const menu =
    open && !disabled
      ? createPortal(
          <ul
            id={listId}
            className="field-select-menu"
            role="listbox"
            aria-labelledby={`${fieldId}-label`}
            style={menuStyle}
          >
            {options.map((option) => {
              const active = option.value === current
              return (
                <li key={option.value} role="presentation">
                  <button
                    type="button"
                    role="option"
                    aria-selected={active}
                    className={`field-select-option${active ? ' is-active' : ''}`}
                    onClick={() => pick(option.value)}
                  >
                    {option.label}
                  </button>
                </li>
              )
            })}
          </ul>,
          document.body,
        )
      : null

  return (
    <div className={`field field-select-wrap ${className}`} ref={rootRef}>
      <span className="field-label" id={`${fieldId}-label`}>
        {label}
      </span>
      <select
        id={fieldId}
        name={name}
        value={current}
        required={required}
        disabled={disabled}
        tabIndex={-1}
        aria-hidden
        className="field-select-native"
        onChange={(e) => emit(e.target.value)}
        {...rest}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>

      <button
        ref={triggerRef}
        type="button"
        className={`field-control field-select-trigger${open ? ' is-open' : ''}`}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-labelledby={`${fieldId}-label`}
        aria-controls={listId}
        onClick={() => !disabled && setOpen((v) => !v)}
        onKeyDown={onTriggerKey}
      >
        <span className="field-select-value">{selectedLabel}</span>
        <ChevronIcon className={`select-chevron${open ? ' is-open' : ''}`} aria-hidden />
      </button>

      {menu}
    </div>
  )
}
