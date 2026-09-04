import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from '../auth'
import { Banner, Button, Card, Field, TextInput, errorMessage } from '../components/ui'

export function LoginPage() {
  const { user, sessionExpired, login } = useAuth()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (user) {
    const from = (location.state as { from?: string } | null)?.from
    return <Navigate to={from ?? '/'} replace />
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login(email, password)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-4 p-6">
      <div>
        <h1 className="text-xl font-semibold">TraceFall</h1>
        <p className="text-[var(--muted)]">Investigator sign-in</p>
      </div>

      {sessionExpired && (
        <Banner tone="warning" title="Your session expired">
          <p>Sign in again to continue. Any unsaved work on the previous screen was not kept.</p>
        </Banner>
      )}

      <Card>
        <form onSubmit={submit} className="flex flex-col gap-3" noValidate>
          <Field label="Email" required>
            {(props) => (
              <TextInput
                {...props}
                type="email"
                name="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            )}
          </Field>
          <Field label="Password" required>
            {(props) => (
              <TextInput
                {...props}
                type="password"
                name="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            )}
          </Field>

          {error && <Banner tone="error" title={error} />}

          <Button type="submit" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>
      </Card>

      <p className="text-xs text-[var(--muted)]">
        Sessions are held in memory only. Reloading this tab signs you out.
      </p>
    </main>
  )
}
