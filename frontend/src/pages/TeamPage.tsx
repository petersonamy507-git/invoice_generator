import { useCallback, useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { teamUsers } from '../api/users'
import type { ApiUser, UserRole } from '../api/types'
import { RowMenu } from '../components/invoice/RowMenu'
import { AppHeader, SectionCard } from '../components/layout/AppChrome'
import { Button } from '../components/ui/Button'
import { Modal } from '../components/ui/Modal'
import { SelectField } from '../components/ui/SelectField'
import { TextField } from '../components/ui/TextField'
import { Toast, useToast } from '../components/ui/Toast'
import { useAuth } from '../context/AuthContext'
import { PlusIcon } from '../components/icons'

type FormMode = 'create' | 'edit' | 'password' | null

const ROLE_OPTIONS = [
  { value: 'user', label: 'User' },
  { value: 'admin', label: 'Admin' },
]

export function TeamPage() {
  const { user, bootstrapping } = useAuth()
  const notify = useToast()
  const [users, setUsers] = useState<ApiUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [mode, setMode] = useState<FormMode>(null)
  const [editing, setEditing] = useState<ApiUser | null>(null)
  const [busy, setBusy] = useState(false)

  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<UserRole>('user')
  const [isActive, setIsActive] = useState(true)
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [formError, setFormError] = useState('')
  const [revealPassword, setRevealPassword] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    notify.showLoading('Loading team logins...')
    try {
      setUsers(await teamUsers.list())
      notify.clear()
    } catch (err) {
      const message = err instanceof ApiError ? err.detail || err.message : 'Unable to load team logins.'
      setError(message)
      notify.showError(message)
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (user?.isAdmin) void refresh()
  }, [user, refresh])

  if (bootstrapping) {
    return (
      <div className="app-shell">
        <main className="page">
          <p className="empty-state">Loading session...</p>
        </main>
        <Toast message="Loading session..." tone="loading" />
      </div>
    )
  }

  if (!user) return <Navigate to="/signin" replace />
  if (!user.isAdmin) return <Navigate to="/" replace />

  const openCreate = () => {
    setEditing(null)
    setUsername('')
    setEmail('')
    setRole('user')
    setIsActive(true)
    setPassword('')
    setConfirmPassword('')
    setFormError('')
    setMode('create')
  }

  const openEdit = (row: ApiUser) => {
    setEditing(row)
    setUsername(row.username)
    setEmail(row.email)
    setRole(row.role === 'admin' ? 'admin' : 'user')
    setIsActive(row.is_active)
    setFormError('')
    setMode('edit')
  }

  const openPassword = (row: ApiUser, showPlain = false) => {
    setEditing(row)
    setPassword('')
    setConfirmPassword('')
    setRevealPassword(showPlain)
    setFormError('')
    setMode('password')
  }

  const closeModal = () => {
    if (busy) return
    setMode(null)
    setEditing(null)
    setFormError('')
  }

  const submit = async () => {
    setFormError('')
    setBusy(true)
    notify.showLoading(mode === 'password' ? 'Updating password...' : 'Saving team login...')
    try {
      if (mode === 'create') {
        if (password.length < 8) throw new Error('Password must be at least 8 characters.')
        if (password !== confirmPassword) throw new Error('Passwords do not match.')
        await teamUsers.create({
          username: username.trim(),
          email: email.trim(),
          password,
          confirm_password: confirmPassword,
          role,
          is_active: isActive,
        })
        notify.showSuccess('Team login created.')
      } else if (mode === 'edit' && editing) {
        await teamUsers.update(editing.id, {
          username: username.trim(),
          email: email.trim(),
          role,
          is_active: isActive,
        })
        notify.showSuccess('Team login updated.')
      } else if (mode === 'password' && editing) {
        if (password.length < 8) throw new Error('Password must be at least 8 characters.')
        if (password !== confirmPassword) throw new Error('Passwords do not match.')
        await teamUsers.setPassword(editing.id, { password, confirm_password: confirmPassword })
        notify.showSuccess('Password updated.')
      }
      setMode(null)
      await refresh()
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.detail || err.message
          : err instanceof Error
            ? err.message
            : 'Request failed.'
      setFormError(message)
      notify.showError(message)
    } finally {
      setBusy(false)
    }
  }

  const removeUser = async (row: ApiUser) => {
    if (row.id === user.id) {
      notify.showError('You cannot delete your own login.')
      return
    }
    if (!window.confirm(`Delete login “${row.username}”?`)) return
    notify.showLoading('Deleting team login...')
    try {
      await teamUsers.remove(row.id)
      notify.showSuccess('Team login deleted.')
      await refresh()
    } catch (err) {
      notify.showError(err instanceof ApiError ? err.detail || err.message : 'Unable to delete login.')
    }
  }

  return (
    <div className="app-shell">
      <AppHeader />
      <main className="page">
        <div className="page-intro reveal">
          <p className="page-kicker">Admin</p>
          <h1>Team access</h1>
          <p>Invite teammates to the portal. Logins are separate from the employee and IBAN list used for invoices.</p>
        </div>

        {error ? (
          <div className="banner-error">
            <span>{error}</span>
            <Button variant="secondary" shape="pill" onClick={() => void refresh()}>
              Retry
            </Button>
          </div>
        ) : null}

        <SectionCard
          step={1}
          title="Portal users"
          aside={
            <Button shape="pill" icon={<PlusIcon />} onClick={openCreate}>
              Add team login
            </Button>
          }
        >
          {loading ? <p className="empty-state">Loading team logins...</p> : null}
          {!loading && users.length === 0 ? <p className="empty-state">No team logins yet.</p> : null}
          {!loading && users.length > 0 ? (
            <>
              <div className="team-cards">
                {users.map((row) => (
                  <article key={row.id} className="team-card">
                    <header>
                      <strong>{row.username}</strong>
                      <span className={`role-pill ${row.role === 'admin' ? 'is-admin' : ''}`}>
                        {row.role === 'admin' ? 'Admin' : 'User'}
                      </span>
                    </header>
                    <p>{row.email}</p>
                    <p className="team-meta">
                      {row.is_active ? 'Active' : 'Inactive'}
                      {row.last_login ? ` · Last login ${row.last_login}` : ' · Never logged in'}
                    </p>
                    <div className="team-actions">
                      <RowMenu
                        items={[
                          { label: 'Edit', onClick: () => openEdit(row) },
                          { label: 'Password', onClick: () => openPassword(row, false) },
                          { label: 'Show password', onClick: () => openPassword(row, true) },
                          { label: 'Delete', onClick: () => void removeUser(row), danger: true },
                        ]}
                      />
                    </div>
                  </article>
                ))}
              </div>
              <div className="table-wrap team-table">
                <table>
                  <thead>
                    <tr>
                      <th>Username</th>
                      <th>Email</th>
                      <th>Role</th>
                      <th>Status</th>
                      <th>Last login</th>
                      <th className="col-action">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((row) => (
                      <tr key={row.id}>
                        <td>{row.username}</td>
                        <td>{row.email}</td>
                        <td>{row.role === 'admin' ? 'Admin' : 'User'}</td>
                        <td>{row.is_active ? 'Active' : 'Inactive'}</td>
                        <td>{row.last_login || '—'}</td>
                        <td className="col-action">
                          <RowMenu
                            items={[
                              { label: 'Edit', onClick: () => openEdit(row) },
                              { label: 'Password', onClick: () => openPassword(row, false) },
                              { label: 'Show password', onClick: () => openPassword(row, true) },
                              { label: 'Delete', onClick: () => void removeUser(row), danger: true },
                            ]}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </SectionCard>
      </main>

      {mode ? (
        <Modal
          title={
            mode === 'create' ? 'Add team login' : mode === 'edit' ? 'Edit team login' : 'Reset password'
          }
          onClose={closeModal}
        >
          <div className="form-grid">
            {mode !== 'password' ? (
              <>
                <TextField label="Username" value={username} onChange={(e) => setUsername(e.target.value)} required />
                <TextField
                  label="Email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
                <SelectField
                  label="Role"
                  value={role}
                  options={ROLE_OPTIONS}
                  onChange={(e) => setRole(e.target.value as UserRole)}
                />
                <label className="field field-check">
                  <span className="field-label">Active</span>
                  <span className="field-control">
                    <input
                      type="checkbox"
                      checked={isActive}
                      onChange={(e) => setIsActive(e.target.checked)}
                    />
                    <span>Can sign in</span>
                  </span>
                </label>
              </>
            ) : null}
            {mode === 'create' || mode === 'password' ? (
              <>
                {mode === 'password' ? (
                  <p className="hint" style={{ gridColumn: '1 / -1', margin: 0 }}>
                    Saved passwords are hashed and cannot be recovered. Set a new password below
                    {revealPassword ? ' (shown as you type)' : ''}. Use the eye icon to show/hide.
                  </p>
                ) : null}
                <TextField
                  key={`pw-${revealPassword}-${editing?.id ?? 'new'}`}
                  label="Password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                  defaultPasswordVisible={revealPassword}
                  required
                />
                <TextField
                  key={`pwc-${revealPassword}-${editing?.id ?? 'new'}`}
                  label="Confirm password"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  autoComplete="new-password"
                  defaultPasswordVisible={revealPassword}
                  required
                />
              </>
            ) : null}
          </div>
          {formError ? <p className="form-error">{formError}</p> : null}
          <div className="modal-actions">
            <Button variant="secondary" onClick={closeModal} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={() => void submit()} disabled={busy}>
              {busy ? 'Saving...' : mode === 'create' ? 'Create login' : mode === 'edit' ? 'Save changes' : 'Update password'}
            </Button>
          </div>
        </Modal>
      ) : null}

      <Toast message={notify.toast.message} tone={notify.toast.tone} onClose={notify.clear} />
    </div>
  )
}
