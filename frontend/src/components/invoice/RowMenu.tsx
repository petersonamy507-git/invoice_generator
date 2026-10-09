import { useEffect, useRef, useState } from 'react'
import { MoreIcon } from '../icons'

export interface RowMenuItem {
  label: string
  onClick: () => void
  danger?: boolean
}

interface RowMenuProps {
  /** Custom menu items (Team page, etc.). */
  items?: RowMenuItem[]
  /** Legacy employee shortcuts when `items` is omitted. */
  onEdit?: () => void
  onRemove?: () => void
}

export function RowMenu({ items, onEdit, onRemove }: RowMenuProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  const menuItems: RowMenuItem[] =
    items ??
    [
      onEdit ? { label: 'Edit record', onClick: onEdit } : null,
      onRemove ? { label: 'Remove', onClick: onRemove, danger: true } : null,
    ].filter(Boolean) as RowMenuItem[]

  useEffect(() => {
    if (!open) return
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="row-menu" ref={rootRef}>
      <button
        type="button"
        className="row-menu-trigger"
        aria-label="Row actions"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <MoreIcon />
      </button>
      {open ? (
        <div className="row-menu-pop" role="menu">
          {menuItems.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              className={item.danger ? 'is-danger' : undefined}
              onClick={() => {
                setOpen(false)
                item.onClick()
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
