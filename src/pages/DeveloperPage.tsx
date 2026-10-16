import { useCallback, useEffect, useMemo, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import {
  developerApi,
  type DevAuditItem,
  type DevColumn,
  type DevFlag,
  type DevTableInfo,
} from '../api/developer'
import { teamUsers } from '../api/users'
import type { ApiUser } from '../api/types'
import { AppHeader, SectionCard } from '../components/layout/AppChrome'
import { Button } from '../components/ui/Button'
import { Modal } from '../components/ui/Modal'
import { SelectField } from '../components/ui/SelectField'
import { TextField } from '../components/ui/TextField'
import { Toast, useToast } from '../components/ui/Toast'
import { useAuth } from '../context/AuthContext'

const BOOL_OPTIONS = [
  { value: '1', label: 'Active (1)' },
  { value: '0', label: 'Inactive (0)' },
]

type PanelTab =
  | 'database'
  | 'sessions'
  | 'users'
  | 'activity'
  | 'api_logs'
  | 'errors'
  | 'flags'
  | 'settings'
  | 'migrations'
  | 'health'
  | 'tools'

const TABS: { id: PanelTab; label: string }[] = [
  { id: 'database', label: 'Database' },
  { id: 'sessions', label: 'Who is online' },
  { id: 'users', label: 'Users & passwords' },
  { id: 'activity', label: 'Activity Trace' },
  { id: 'api_logs', label: 'API Logs' },
  { id: 'errors', label: 'Error Logs' },
  { id: 'flags', label: 'Feature Flags' },
  { id: 'settings', label: 'Settings' },
  { id: 'migrations', label: 'Migrations' },
  { id: 'health', label: 'Health' },
  { id: 'tools', label: 'Tools' },
]

const CONFIRM_PHRASE = 'CONFIRM'

const BOOL_COLUMNS = new Set([
  'is_active',
  'enabled',
  'active',
  'is_admin',
  'is_deleted',
  'deleted',
])

function isBoolColumn(name: string): boolean {
  return BOOL_COLUMNS.has(String(name || '').toLowerCase())
}

function isPasswordColumn(name: string): boolean {
  const n = String(name || '').toLowerCase()
  return n === 'password_hash' || n === 'password' || n.endsWith('_hash')
}

function asBool(v: unknown): boolean {
  if (typeof v === 'boolean') return v
  if (typeof v === 'number') return v !== 0
  const s = String(v ?? '').trim().toLowerCase()
  return s === '1' || s === 'true' || s === 'yes' || s === 'on'
}

/** Table / read-only display formatting. */
function formatDisplay(column: string, v: unknown): string {
  if (v === null || v === undefined) return ''
  if (isBoolColumn(column)) return asBool(v) ? 'Active' : 'Inactive'
  if (isPasswordColumn(column)) {
    const raw = String(v)
    if (!raw) return ''
    if (raw.includes('REDACTED')) return '••••••••'
    // Full hash visible to developers (plaintext is never stored).
    if (raw.startsWith('$2')) return raw
    return raw
  }
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

/** Editor input value (keep 1/0 editable as Active select elsewhere). */
function editorTextValue(column: string, v: unknown): string {
  if (v === null || v === undefined) return ''
  if (isPasswordColumn(column)) {
    // Don't dump full hash into the input — empty means keep existing on edit.
    return ''
  }
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

export function DeveloperPage() {
  const { user, bootstrapping } = useAuth()
  const notify = useToast()
  const [tab, setTab] = useState<PanelTab>('database')
  const [environment, setEnvironment] = useState('development')

  const [tables, setTables] = useState<DevTableInfo[]>([])
  const [table, setTable] = useState('')
  const [columns, setColumns] = useState<DevColumn[]>([])
  const [pk, setPk] = useState<string[]>([])
  const [rows, setRows] = useState<Record<string, unknown>[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [editorOpen, setEditorOpen] = useState(false)
  const [editorMode, setEditorMode] = useState<'create' | 'edit'>('edit')
  const [editorRow, setEditorRow] = useState<Record<string, unknown>>({})
  const [editorPk, setEditorPk] = useState<Record<string, unknown>>({})
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [confirmAction, setConfirmAction] = useState<'delete' | 'bulk-delete' | 'clear-logs' | null>(null)
  const [confirmPhrase, setConfirmPhrase] = useState('')
  const [prodPassword, setProdPassword] = useState('')
  const [busy, setBusy] = useState(false)

  const [users, setUsers] = useState<ApiUser[]>([])
  const [audit, setAudit] = useState<DevAuditItem[]>([])
  const [sessions, setSessions] = useState<Record<string, unknown>[]>([])
  const [credOpen, setCredOpen] = useState(false)
  const [credJson, setCredJson] = useState('')
  const [logs, setLogs] = useState<Record<string, unknown>[]>([])
  const [flags, setFlags] = useState<DevFlag[]>([])
  const [jsonPanel, setJsonPanel] = useState<string>('')

  const limit = 50
  const isProd = environment === 'production' || environment === 'prod'
  const [searchInput, setSearchInput] = useState('')
  const [dbReloadToken, setDbReloadToken] = useState(0)

  useEffect(() => {
    if (!user?.isDeveloper) return
    let cancelled = false
    void developerApi
      .overview()
      .then((ov) => {
        if (!cancelled) setEnvironment(String(ov.environment || 'development'))
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [user?.isDeveloper])

  // Database tab only — stable deps (do not depend on toast helpers).
  useEffect(() => {
    if (!user?.isDeveloper || tab !== 'database') return
    let cancelled = false
    void (async () => {
      try {
        const tablesRes = await developerApi.tables()
        if (cancelled) return
        const list = tablesRes.tables || []
        setTables(list)
        const active = table || list[0]?.name || ''
        if (!table && active) {
          setTable(active)
          return
        }
        if (!active) return
        const res = await developerApi.rows(active, { limit, offset, search })
        if (cancelled) return
        setRows(res.rows || [])
        setColumns(res.columns || [])
        setPk(res.primary_key || [])
        setTotal(res.total || 0)
        setSelected(new Set())
      } catch (err) {
        if (!cancelled) {
          notify.showError(err instanceof ApiError ? err.detail : 'Failed to load rows')
        }
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- notify helpers are unstable
  }, [user?.isDeveloper, tab, table, offset, search, dbReloadToken, limit])

  // Non-database panels — fetch once when the tab changes.
  useEffect(() => {
    if (!user?.isDeveloper || tab === 'database') return
    let cancelled = false
    void (async () => {
      try {
        if (tab === 'users') {
          const list = await teamUsers.list()
          if (!cancelled) setUsers(list)
        } else if (tab === 'sessions') {
          const res = await developerApi.sessions()
          if (!cancelled) setSessions(res.sessions || [])
        } else if (tab === 'activity') {
          const res = await developerApi.activity({ limit: 150 })
          if (!cancelled) setAudit(res.items || [])
        } else if (tab === 'api_logs') {
          const res = await developerApi.apiLogs({ limit: 100 })
          if (!cancelled) setLogs(res.items || [])
        } else if (tab === 'errors') {
          const res = await developerApi.errorLogs()
          if (!cancelled) setLogs(res.items || [])
        } else if (tab === 'flags') {
          const res = await developerApi.flags()
          if (!cancelled) setFlags(res.flags || [])
        } else if (tab === 'settings') {
          const data = await developerApi.settings()
          if (!cancelled) setJsonPanel(JSON.stringify(data, null, 2))
        } else if (tab === 'migrations') {
          const data = await developerApi.migrations()
          if (!cancelled) setJsonPanel(JSON.stringify(data, null, 2))
        } else if (tab === 'health') {
          const data = await developerApi.health()
          if (!cancelled) setJsonPanel(JSON.stringify(data, null, 2))
        } else if (tab === 'tools') {
          const [jobs, webhooks] = await Promise.all([developerApi.jobs(), developerApi.webhooks()])
          if (!cancelled) setJsonPanel(JSON.stringify({ jobs, webhooks }, null, 2))
        }
      } catch (err) {
        if (!cancelled) {
          notify.showError(err instanceof ApiError ? err.detail : 'Failed to load panel')
        }
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- notify helpers are unstable
  }, [user?.isDeveloper, tab])

  const reloadDatabase = useCallback(() => {
    setDbReloadToken((n) => n + 1)
  }, [])

  const reloadFlags = useCallback(async () => {
    try {
      const res = await developerApi.flags()
      setFlags(res.flags || [])
    } catch (err) {
      notify.showError(err instanceof ApiError ? err.detail : 'Flag reload failed')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const writableColumns = useMemo(
    () => columns.filter((c) => !pk.includes(c.name)),
    [columns, pk],
  )

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
  if (!user.isDeveloper) return <Navigate to="/" replace />

  const openCreate = () => {
    const blank: Record<string, unknown> = {}
    columns.forEach((c) => {
      blank[c.name] = ''
    })
    setEditorMode('create')
    setEditorRow(blank)
    setEditorPk({})
    setEditorOpen(true)
  }

  const openEdit = (row: Record<string, unknown>) => {
    const nextPk: Record<string, unknown> = {}
    pk.forEach((k) => {
      nextPk[k] = row[k]
    })
    setEditorMode('edit')
    setEditorPk(nextPk)
    setEditorRow({ ...row })
    setEditorOpen(true)
  }

  const saveEditor = async () => {
    setBusy(true)
    try {
      if (editorMode === 'create') {
        const data: Record<string, unknown> = {}
        columns.forEach((c) => {
          let v = editorRow[c.name]
          if (isBoolColumn(c.name)) v = asBool(v) ? 1 : 0
          if (isPasswordColumn(c.name) && (v === '' || v == null)) return
          data[c.name] = v
        })
        await developerApi.createRow(table, data)
        notify.showSuccess('Record created')
      } else {
        const data: Record<string, unknown> = {}
        writableColumns.forEach((c) => {
          let v = editorRow[c.name]
          if (isPasswordColumn(c.name) && (v === '' || v == null)) return // keep existing hash
          if (isBoolColumn(c.name)) v = asBool(v) ? 1 : 0
          data[c.name] = v
        })
        await developerApi.updateRow(table, editorPk, data)
        notify.showSuccess('Record updated')
      }
      setEditorOpen(false)
      reloadDatabase()
    } catch (err) {
      notify.showError(err instanceof ApiError ? err.detail : 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  const runConfirmed = async () => {
    if (confirmPhrase !== CONFIRM_PHRASE) {
      notify.showError(`Type ${CONFIRM_PHRASE} to confirm`)
      return
    }
    setBusy(true)
    const confirm = {
      confirm: true,
      confirm_phrase: CONFIRM_PHRASE,
      production_password: isProd ? prodPassword : undefined,
    }
    try {
      if (confirmAction === 'delete') {
        await developerApi.deleteRow(table, editorPk, confirm)
        notify.showSuccess('Record deleted')
        setEditorOpen(false)
        reloadDatabase()
      } else if (confirmAction === 'bulk-delete') {
        const pk_list = [...selected].map((idx) => {
          const row = rows[idx]
          const p: Record<string, unknown> = {}
          pk.forEach((k) => {
            p[k] = row[k]
          })
          return p
        })
        await developerApi.bulkDelete(table, pk_list, confirm)
        notify.showSuccess(`Deleted ${pk_list.length} rows`)
        reloadDatabase()
      } else if (confirmAction === 'clear-logs') {
        await developerApi.clearApiLogs(confirm)
        notify.showSuccess('API logs cleared')
        const res = await developerApi.apiLogs({ limit: 100 })
        setLogs(res.items || [])
      }
      setConfirmOpen(false)
      setConfirmPhrase('')
      setProdPassword('')
      setConfirmAction(null)
    } catch (err) {
      notify.showError(err instanceof ApiError ? err.detail : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  const toggleFlag = async (flag: DevFlag) => {
    try {
      await developerApi.upsertFlag({
        flag_key: flag.flag_key,
        enabled: !flag.enabled,
        description: flag.description || undefined,
      })
      notify.showSuccess(`Flag ${flag.flag_key} updated`)
      await reloadFlags()
    } catch (err) {
      notify.showError(err instanceof ApiError ? err.detail : 'Flag update failed')
    }
  }

  return (
    <div className="app-shell">
      <AppHeader />
      <main className="page developer-page">
        <div className="page-intro">
          <div>
            <p className="page-kicker">Developer</p>
            <h1>Developer Panel</h1>
            <p className="muted">
              Full technical control — env <strong>{environment}</strong>. Destructive actions require typing{' '}
              <code>{CONFIRM_PHRASE}</code>
              {isProd ? ' plus password re-auth.' : '.'}
            </p>
          </div>
        </div>

        <div className="dev-tabs" role="tablist" aria-label="Developer panels">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              className={`dev-tab ${tab === t.id ? 'is-active' : ''}`}
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === 'database' ? (
          <SectionCard step={1} title="Database Explorer">
            <div className="dev-db-toolbar">
              <label className="field">
                <span>Table</span>
                <select value={table} onChange={(e) => { setOffset(0); setTable(e.target.value) }}>
                  {tables.map((t) => (
                    <option key={t.name} value={t.name}>
                      {t.name}
                      {t.approx_rows != null ? ` (~${t.approx_rows})` : ''}
                    </option>
                  ))}
                </select>
              </label>
              <TextField
                label="Search"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
              />
              <Button
                type="button"
                onClick={() => {
                  setOffset(0)
                  setSearch(searchInput)
                  reloadDatabase()
                }}
              >
                Search
              </Button>
              <Button type="button" variant="secondary" onClick={openCreate}>
                Create record
              </Button>
              <Button
                type="button"
                variant="danger"
                disabled={selected.size === 0}
                onClick={() => {
                  setConfirmAction('bulk-delete')
                  setConfirmOpen(true)
                }}
              >
                Bulk delete ({selected.size})
              </Button>
            </div>

            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th />
                    {columns.map((c) => (
                      <th key={c.name}>
                        {c.name}
                        {c.sensitive ? ' 🔒' : ''}
                      </th>
                    ))}
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, idx) => (
                    <tr key={idx}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selected.has(idx)}
                          onChange={(e) => {
                            const next = new Set(selected)
                            if (e.target.checked) next.add(idx)
                            else next.delete(idx)
                            setSelected(next)
                          }}
                        />
                      </td>
                      {columns.map((c) => (
                        <td key={c.name}>
                          {isBoolColumn(c.name) ? (
                            <span className={`role-pill ${asBool(row[c.name]) ? 'is-admin' : ''}`}>
                              {formatDisplay(c.name, row[c.name])}
                            </span>
                          ) : isPasswordColumn(c.name) ? (
                            <code className="dev-cell dev-cell-hash" title={String(row[c.name] ?? '')}>
                              {formatDisplay(c.name, row[c.name])}
                            </code>
                          ) : (
                            <code className="dev-cell">{formatDisplay(c.name, row[c.name])}</code>
                          )}
                        </td>
                      ))}
                      <td>
                        <Button type="button" variant="secondary" onClick={() => openEdit(row)}>
                          Edit
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="dev-pager">
              <span>
                {total} rows · showing {offset + 1}–{Math.min(offset + limit, total)}
              </span>
              <div className="inline-actions">
                <Button type="button" variant="secondary" disabled={offset <= 0} onClick={() => setOffset(Math.max(0, offset - limit))}>
                  Prev
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={offset + limit >= total}
                  onClick={() => setOffset(offset + limit)}
                >
                  Next
                </Button>
              </div>
            </div>
          </SectionCard>
        ) : null}

        {tab === 'sessions' ? (
          <SectionCard step={1} title="Who is currently logged in">
            <p className="muted">Active sessions — every login across Admin, Developer, and User.</p>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Role</th>
                    <th>IP</th>
                    <th>Started</th>
                    <th>Expires</th>
                    <th>Last login</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {sessions.map((s) => (
                    <tr key={String(s.session_id)}>
                      <td>
                        <strong>{String(s.username || '')}</strong>
                        <div className="muted">{String(s.email || '')}</div>
                      </td>
                      <td>{String(s.role || '')}</td>
                      <td>{String(s.ip_address || '—')}</td>
                      <td>{String(s.session_started || '')}</td>
                      <td>{String(s.expires_at || '')}</td>
                      <td>{String(s.last_login || '—')}</td>
                      <td>
                        <Button
                          type="button"
                          variant="danger"
                          onClick={() => {
                            void (async () => {
                              try {
                                await developerApi.revokeSession(String(s.session_id))
                                notify.showSuccess('Session revoked')
                                const res = await developerApi.sessions()
                                setSessions(res.sessions || [])
                              } catch (err) {
                                notify.showError(err instanceof ApiError ? err.detail : 'Revoke failed')
                              }
                            })()
                          }}
                        >
                          Force logout
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {sessions.length === 0 ? <p className="empty-state">No active sessions.</p> : null}
          </SectionCard>
        ) : null}

        {tab === 'users' ? (
          <SectionCard step={1} title="Users & password hashes">
            <p className="muted">
              Plaintext passwords are never stored. Developers can view the full <code>password_hash</code> and set a new password for any account.
            </p>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Username</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Active</th>
                    <th>Last login</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id}>
                      <td>{u.id}</td>
                      <td>{u.username}</td>
                      <td>{u.email}</td>
                      <td>
                        <span className={`role-pill ${u.role === 'developer' ? 'is-dev' : u.role === 'admin' ? 'is-admin' : ''}`}>
                          {u.role}
                        </span>
                      </td>
                      <td>{u.is_active ? 'Active' : 'Inactive'}</td>
                      <td>{u.last_login || '—'}</td>
                      <td>
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() => {
                            void (async () => {
                              try {
                                const cred = await developerApi.userCredentials(u.id)
                                setCredJson(JSON.stringify(cred, null, 2))
                                setCredOpen(true)
                              } catch (err) {
                                notify.showError(err instanceof ApiError ? err.detail : 'Failed to load credentials')
                              }
                            })()
                          }}
                        >
                          View hash
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted">Edit users in Team, or open the <code>users</code> table in Database to change any field / password.</p>
          </SectionCard>
        ) : null}

        {tab === 'activity' ? (
          <SectionCard step={1} title="Activity Trace">
            <p className="muted">
              Full trail — logins, employee add/update/delete, user changes, password resets, invoice API calls, and Developer DB edits.
            </p>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Who</th>
                    <th>Action</th>
                    <th>Target</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.map((a) => (
                    <tr key={a.id}>
                      <td>{a.created_at}</td>
                      <td>{a.actor_username || '—'}</td>
                      <td>
                        <code>{a.action}</code>
                      </td>
                      <td>
                        {a.table_name || a.resource_type}
                        {a.resource_id ? ` · ${a.resource_id}` : ''}
                      </td>
                      <td>
                        <details>
                          <summary>View before / after</summary>
                          <pre className="dev-json">{JSON.stringify({ before: a.before, after: a.after }, null, 2)}</pre>
                        </details>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {audit.length === 0 ? <p className="empty-state">No activity yet — add an employee or sign in to generate traces.</p> : null}
          </SectionCard>
        ) : null}

        {tab === 'api_logs' || tab === 'errors' ? (
          <SectionCard step={1} title={tab === 'errors' ? 'Error Logs' : 'API Logs'}>
            {tab === 'api_logs' ? (
              <div className="inline-actions" style={{ marginBottom: 12 }}>
                <Button
                  type="button"
                  variant="danger"
                  onClick={() => {
                    setConfirmAction('clear-logs')
                    setConfirmOpen(true)
                  }}
                >
                  Clear API logs
                </Button>
              </div>
            ) : null}
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Method</th>
                    <th>Path</th>
                    <th>Status</th>
                    <th>ms</th>
                    <th>Error</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((l) => (
                    <tr key={String(l.id)}>
                      <td>{String(l.created_at || '')}</td>
                      <td>{String(l.method || '')}</td>
                      <td>{String(l.path || '')}</td>
                      <td>{String(l.status_code || '')}</td>
                      <td>{String(l.duration_ms ?? '')}</td>
                      <td>{String(l.error_detail || '')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
        ) : null}

        {tab === 'flags' ? (
          <SectionCard step={1} title="Feature Flags">
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Flag</th>
                    <th>Enabled</th>
                    <th>Description</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {flags.map((f) => (
                    <tr key={f.flag_key}>
                      <td>
                        <code>{f.flag_key}</code>
                      </td>
                      <td>{f.enabled ? 'on' : 'off'}</td>
                      <td>{f.description}</td>
                      <td>
                        <Button type="button" variant="secondary" onClick={() => void toggleFlag(f)}>
                          Toggle
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
        ) : null}

        {['settings', 'migrations', 'health', 'tools'].includes(tab) ? (
          <SectionCard step={1} title={TABS.find((t) => t.id === tab)?.label || 'Panel'}>
            <pre className="dev-json">{jsonPanel || 'Loading...'}</pre>
          </SectionCard>
        ) : null}
      </main>

      {editorOpen ? (
        <Modal
          title={editorMode === 'create' ? `Create · ${table}` : `Edit · ${table}`}
          onClose={() => setEditorOpen(false)}
        >
          <div className="form-grid">
            {(editorMode === 'create' ? columns : writableColumns).map((c) => {
              const label = `${c.name}${pk.includes(c.name) ? ' (PK)' : ''}`
              const disabled = editorMode === 'edit' && pk.includes(c.name)
              if (isBoolColumn(c.name)) {
                return (
                  <SelectField
                    key={c.name}
                    label={label}
                    value={asBool(editorRow[c.name]) ? '1' : '0'}
                    options={BOOL_OPTIONS}
                    disabled={disabled}
                    onChange={(e) =>
                      setEditorRow((prev) => ({ ...prev, [c.name]: e.target.value === '1' ? 1 : 0 }))
                    }
                  />
                )
              }
              if (isPasswordColumn(c.name)) {
                return (
                  <TextField
                    key={c.name}
                    label={`${label} — new password (leave blank to keep)`}
                    type="password"
                    value={editorTextValue(c.name, editorRow[c.name])}
                    disabled={disabled}
                    onChange={(e) => setEditorRow((prev) => ({ ...prev, [c.name]: e.target.value }))}
                  />
                )
              }
              return (
                <TextField
                  key={c.name}
                  label={label}
                  value={editorTextValue(c.name, editorRow[c.name])}
                  disabled={disabled}
                  onChange={(e) => setEditorRow((prev) => ({ ...prev, [c.name]: e.target.value }))}
                />
              )
            })}
          </div>
          <div className="modal-actions">
            {editorMode === 'edit' ? (
              <Button
                type="button"
                variant="danger"
                onClick={() => {
                  setConfirmAction('delete')
                  setConfirmOpen(true)
                }}
              >
                Delete
              </Button>
            ) : null}
            <Button type="button" variant="secondary" onClick={() => setEditorOpen(false)}>
              Cancel
            </Button>
            <Button type="button" disabled={busy} onClick={() => void saveEditor()}>
              Save
            </Button>
          </div>
        </Modal>
      ) : null}

      {credOpen ? (
        <Modal title="User credentials" onClose={() => setCredOpen(false)}>
          <p className="muted">Full password hash (plaintext cannot be recovered from the database).</p>
          <pre className="dev-json">{credJson}</pre>
          <div className="modal-actions">
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                void navigator.clipboard?.writeText(credJson)
                notify.showSuccess('Copied')
              }}
            >
              Copy JSON
            </Button>
            <Button type="button" onClick={() => setCredOpen(false)}>
              Close
            </Button>
          </div>
        </Modal>
      ) : null}

      {confirmOpen ? (
        <Modal title="Confirm destructive action" onClose={() => setConfirmOpen(false)}>
          <p>
            Type <code>{CONFIRM_PHRASE}</code> to proceed
            {isProd ? ' and re-enter your password.' : '.'}
          </p>
          <TextField label="Confirmation phrase" value={confirmPhrase} onChange={(e) => setConfirmPhrase(e.target.value)} />
          {isProd ? (
            <TextField
              label="Your password"
              type="password"
              value={prodPassword}
              onChange={(e) => setProdPassword(e.target.value)}
            />
          ) : null}
          <div className="modal-actions">
            <Button type="button" variant="secondary" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button type="button" variant="danger" disabled={busy} onClick={() => void runConfirmed()}>
              Confirm
            </Button>
          </div>
        </Modal>
      ) : null}

      <Toast message={notify.toast.message} tone={notify.toast.tone} onClose={notify.clear} />
    </div>
  )
}
