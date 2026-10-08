import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { LogoMark, LogoutIcon, MoonIcon, SunIcon } from '../icons'
import { useAuth } from '../../context/AuthContext'
import { useTheme } from '../../context/ThemeContext'
import { initials } from '../../utils/format'

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`logo ${compact ? 'logo-compact' : ''}`}>
      <LogoMark />
      <span className="logo-text">
        North<span>line</span>
      </span>
    </span>
  )
}

export function AppHeader() {
  const { user, signOut } = useAuth()
  const { theme, toggleTheme } = useTheme()
  if (!user) return null

  return (
    <header className="app-header">
      <div className="header-brand">
        <Logo />
        <nav className="header-nav" aria-label="Main">
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'is-active' : undefined)}>
            Invoices
          </NavLink>
          {user.isAdmin ? (
            <NavLink to="/team" className={({ isActive }) => (isActive ? 'is-active' : undefined)}>
              Team
            </NavLink>
          ) : null}
        </nav>
      </div>
      <div className="header-actions">
        <button type="button" className="icon-button" onClick={toggleTheme} aria-label="Toggle color theme">
          {theme === 'dark' ? <MoonIcon /> : <SunIcon />}
        </button>
        <div className="user-chip">
          <span className="avatar" aria-hidden="true">
            {initials(user.name)}
          </span>
          <span className="user-meta">
            <strong>{user.name}</strong>
            <small>{user.roleLabel}</small>
          </span>
        </div>
        <button type="button" className="icon-button icon-button-quiet" onClick={() => void signOut()} aria-label="Log out">
          <LogoutIcon />
        </button>
      </div>
    </header>
  )
}

export function SectionCard({
  step,
  title,
  aside,
  children,
}: {
  step: number
  title: string
  aside?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="panel reveal">
      <header className="panel-head">
        <h2>
          <span className="step-index">{String(step).padStart(2, '0')}</span>
          {title}
        </h2>
        {aside}
      </header>
      {children}
    </section>
  )
}
