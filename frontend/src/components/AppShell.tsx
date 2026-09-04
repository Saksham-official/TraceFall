import { useEffect, useState } from 'react'
import { Link, Outlet } from 'react-router-dom'

import { useHealth } from '../api/queries'
import { useAuth } from '../auth'
import { Banner, Button } from './ui'

type Theme = 'system' | 'light' | 'dark'
const THEME_KEY = 'tracefall.theme'
const NEXT: Record<Theme, Theme> = { system: 'light', light: 'dark', dark: 'system' }

/** A display preference, not a credential — localStorage is the right home for it. */
function readTheme(): Theme {
  const stored = localStorage.getItem(THEME_KEY)
  return stored === 'light' || stored === 'dark' ? stored : 'system'
}

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readTheme)

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') {
      root.removeAttribute('data-theme')
      localStorage.removeItem(THEME_KEY)
    } else {
      root.setAttribute('data-theme', theme)
      localStorage.setItem(THEME_KEY, theme)
    }
  }, [theme])

  return (
    <Button
      variant="ghost"
      onClick={() => setTheme(NEXT[theme])}
      aria-label={`Theme: ${theme}. Switch to ${NEXT[theme]}.`}
    >
      Theme: {theme}
    </Button>
  )
}

export function AppShell() {
  const { user, logout } = useAuth()
  const health = useHealth()

  return (
    <div className="min-h-screen">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:m-2 focus:rounded focus:bg-[var(--surface)] focus:p-2"
      >
        Skip to main content
      </a>

      <header className="flex flex-wrap items-center gap-3 border-b border-[var(--border)] bg-[var(--surface)] px-4 py-2">
        <Link to="/" className="font-semibold">
          TraceFall
        </Link>
        <span className="ml-auto text-[var(--muted)]">
          {user?.full_name} · {user?.role}
        </span>
        <ThemeToggle />
        <Button variant="secondary" onClick={() => void logout()}>
          Sign out
        </Button>
      </header>

      {/* NFR-15: presenting cached data as live, even by omission, is not acceptable. */}
      {health.data && !health.data.live_mode && (
        <div className="px-4 pt-3">
          <Banner tone="warning" title="Cached snapshot — not live blockchain data">
            <p>
              This instance runs with <code className="font-mono">LIVE_MODE=false</code>. Blockchain
              retrieval is served from the committed fixture cache.
            </p>
          </Banner>
        </div>
      )}

      <main id="main" className="mx-auto max-w-6xl p-4">
        <Outlet />
      </main>
    </div>
  )
}
