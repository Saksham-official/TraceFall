import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'

import { useAuth } from '../auth'
import { LogoMark, Wordmark } from '../components/Logo'
import {
  ArrowRightIcon,
  BuildingIcon,
  FileTextIcon,
  GitBranchIcon,
  ShieldCheckIcon,
} from '../components/icons'
import { Banner, Button, Card, Field, TextInput, errorMessage } from '../components/ui'

const PROOF = [
  {
    Icon: GitBranchIcon,
    title: 'Follow the money, hop by hop',
    body: 'Multi-hop fund flow across TRON and Ethereum, with proportional value attribution stated on every trace.',
  },
  {
    Icon: BuildingIcon,
    title: 'Name the exchange, with its evidence',
    body: 'Every entity claim carries one tier — confirmed, likely, or unattributed — and the signals behind it.',
  },
  {
    Icon: FileTextIcon,
    title: 'A report for the case file',
    body: 'Every conclusion traces to transaction hashes. Deterministic, inspectable, and hashed on generation.',
  },
]

const PIPELINE = ['Retrieve', 'Trace', 'Graph', 'Patterns', 'Attribute', 'Risk', 'Report']

// Public, demo-only access for reviewers. This account has no production data or
// privileges beyond the deterministic showcase workspace.
const DEMO_EMAIL = 'investigator@tracefall.gov'
const DEMO_PASSWORD = 'TraceFall2026!'

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

  async function startDemo() {
    setError(null)
    setBusy(true)
    try {
      await login(DEMO_EMAIL, DEMO_PASSWORD)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="grid min-h-screen lg:grid-cols-[1.15fr_1fr]">
      {/* Product side */}
      <section className="relative hidden flex-col justify-between overflow-hidden border-r border-[var(--border)] bg-[var(--surface)] p-10 lg:flex xl:p-14">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-[0.35]"
          style={{
            backgroundImage:
              'linear-gradient(var(--border) 1px, transparent 1px), linear-gradient(90deg, var(--border) 1px, transparent 1px)',
            backgroundSize: '32px 32px',
            maskImage: 'radial-gradient(ellipse at 30% 20%, black 20%, transparent 70%)',
          }}
        />
        <div className="relative flex items-center gap-2">
          <LogoMark className="h-7 w-7" />
          <Wordmark className="text-lg" />
        </div>

        <div className="relative max-w-xl">
          <p className="text-label mb-3 text-[var(--accent)]">Blockchain intelligence for investigators</p>
          <h2 className="text-display text-[2.25rem] leading-[2.6rem]">
            Investigate crypto crime faster.
          </h2>
          <p className="text-secondary mt-4 max-w-lg text-[0.9375rem] leading-6 text-[var(--muted)]">
            Turn a victim-reported wallet address into an evidenced answer to one question:
            where did the money go, and which exchange do I send the freeze request to?
          </p>

          <ol className="mt-8 flex flex-wrap items-center gap-y-2" aria-label="Analysis pipeline">
            {PIPELINE.map((step, index) => (
              <li key={step} className="flex items-center">
                <span className="rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--bg)] px-2 py-1 text-xs font-medium text-[var(--text-2)]">
                  {step}
                </span>
                {index < PIPELINE.length - 1 && (
                  <ArrowRightIcon className="mx-1 h-3 w-3 text-[var(--border-strong)]" />
                )}
              </li>
            ))}
          </ol>

          <ul className="mt-10 grid gap-5">
            {PROOF.map(({ Icon, title, body }) => (
              <li key={title} className="flex gap-3">
                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius)] bg-[var(--accent-soft)] text-[var(--accent)]">
                  <Icon className="h-4 w-4" />
                </span>
                <div>
                  <p className="font-semibold">{title}</p>
                  <p className="text-secondary mt-0.5 text-[var(--muted)]">{body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="text-meta relative flex items-center gap-1.5">
          <ShieldCheckIcon className="h-3.5 w-3.5" />
          Read-only against every blockchain. No keys held, no funds moved, no victim data stored.
        </p>
      </section>

      {/* Sign-in side */}
      <section className="flex flex-col justify-center px-6 py-10 sm:px-12">
        <div className="mx-auto w-full max-w-sm">
          <div className="mb-6 flex items-center gap-2 lg:hidden">
            <LogoMark className="h-7 w-7" />
            <Wordmark className="text-lg" />
          </div>
          <h1 className="text-h1">TraceFall</h1>
          <p className="text-secondary mt-1 text-[var(--muted)]">Investigator sign-in</p>

          {sessionExpired && (
            <Banner tone="warning" title="Your session expired" className="mt-5">
              <p>Sign in again to continue. Any unsaved work on the previous screen was not kept.</p>
            </Banner>
          )}

          <Card className="mt-5">
            <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
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

              {error && <Banner tone="error" title={error} compact />}

              <Button type="submit" loading={busy} className="mt-1 w-full">
                {busy ? 'Signing in…' : 'Sign in'}
              </Button>
            </form>
          </Card>

          <Card className="mt-3 border-[var(--accent)]/25 bg-[var(--accent-soft)]">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="font-semibold">Explore the demo workspace</p>
                <p className="text-meta mt-0.5">Open the prepared investigation in one click.</p>
              </div>
              <Button
                type="button"
                variant="secondary"
                loading={busy}
                onClick={() => void startDemo()}
                className="shrink-0 border-[var(--accent)]/35 text-[var(--accent)] hover:border-[var(--accent)]"
              >
                Get started
              </Button>
            </div>
          </Card>

          <p className="text-meta mt-4">
            Your access token is held in memory only; the refresh cookie that survives a reload is
            httpOnly, so no script on this page can read it.
          </p>
          <p className="text-secondary mt-6">
            <Link
              to="/welcome"
              className="inline-flex items-center gap-1 font-medium text-[var(--accent)] hover:underline"
            >
              About TraceFall <ArrowRightIcon className="h-3 w-3" />
            </Link>
          </p>
        </div>
      </section>
    </main>
  )
}
