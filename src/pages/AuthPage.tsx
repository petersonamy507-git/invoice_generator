import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { LockIcon, MailIcon } from '../components/icons'
import { Logo } from '../components/layout/AppChrome'
import { Button } from '../components/ui/Button'
import { TextField } from '../components/ui/TextField'
import { Toast, useToast } from '../components/ui/Toast'

export function AuthPage() {
  const { user, bootstrapping } = useAuth()
  if (bootstrapping) {
    return (
      <main className="auth-screen">
        <div className="auth-shell auth-loading-shell">
          <span className="toast-spinner" aria-hidden="true" />
          <p>Checking session...</p>
        </div>
        <Toast message="Loading session..." tone="loading" />
      </main>
    )
  }
  if (user) return <Navigate to="/" replace />
  return <AuthForm />
}

function AuthForm() {
  const { signIn } = useAuth()
  const navigate = useNavigate()
  const notify = useToast()
  const [identifier, setIdentifier] = useState('admin')
  const [password, setPassword] = useState('Admin@12345')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    notify.showLoading('Signing in...')
    const message = await signIn(identifier, password)
    setBusy(false)
    if (message) {
      setError(message)
      notify.showError(message)
      return
    }
    notify.showSuccess('Signed in successfully.')
    navigate('/')
  }

  return (
    <main className="auth-screen">
      <div className="auth-shell reveal">
        <aside className="auth-hero" aria-label="Product">
          <Logo />
          <h1>Invoices that look like your brand.</h1>
          <p>Select people, pick a template, and download a polished PDF ZIP — built for payroll teams who ship every week.</p>
          <ul className="auth-points">
            <li>14 company invoice templates</li>
            <li>Department filters &amp; bulk generate</li>
            <li>Admin-managed team access</li>
          </ul>
        </aside>
        <section className="auth-panel">
          <form className="auth-form" onSubmit={(event) => void submit(event)}>
            <p className="auth-kicker">Welcome back</p>
            <h2 className="auth-title">Sign in to Northline</h2>
            <p className="auth-sub">Use the username or email issued by your admin.</p>
            <TextField
              label="Username or Email"
              icon={<MailIcon />}
              autoComplete="username"
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
            />
            <TextField
              label="Password"
              type="password"
              icon={<LockIcon />}
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            {error ? <p className="form-error">{error}</p> : null}
            <Button type="submit" fullWidth disabled={busy}>
              {busy ? 'Signing in...' : 'Continue'}
            </Button>
          </form>
        </section>
      </div>
      <Toast message={notify.toast.message} tone={notify.toast.tone} onClose={notify.clear} />
    </main>
  )
}
