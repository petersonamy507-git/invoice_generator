import { LayersIcon } from '../icons'
import type { Department } from '../../types'

interface DepartmentCardProps {
  department: Department
  count: number
  active: boolean
  onSelect: () => void
}

export function DepartmentCard({ department, count, active, onSelect }: DepartmentCardProps) {
  return (
    <button
      type="button"
      className={`dept-chip ${active ? 'is-active' : ''}`}
      aria-pressed={active}
      onClick={onSelect}
    >
      <span className="dept-chip-icon" aria-hidden="true">
        <LayersIcon />
      </span>
      <span className="dept-chip-copy">
        <span className="dept-name">{department.badgeName || department.name}</span>
        <span className="dept-count">{count}</span>
      </span>
    </button>
  )
}
