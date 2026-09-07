import { useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'

import { useHealth } from '../api/queries'
import { canEdit, useAuth } from '../auth'
import { applyTheme, readTheme } from '../lib/theme'
import type { Theme } from '../lib/theme'
import { LogoMark, Wordmark } from './Logo'
import { FolderIcon, LogOutIcon, MoonIcon, PlusIcon, SunIcon, UserIcon } from './icons'
import { IconButton } from './ui'

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readTheme)
  const next: Theme = theme === 'dark' ? 'light' : 'dark'

  function toggle() {
    applyTheme(next)
    setTheme(next)
  }

  return (
    <IconButton label={`Switch to ${next} theme`} onClick={toggle}>
      {theme === 'dark' ? <SunIcon className="h-4 w-4" /> : <MoonIcon className="h-4 w-4" />}
    </IconButton>
  )
}

const NAV_LINK =
  'transition-ui inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-sm)] px-2.5 text-sm font-medium'

function navClass({ isActive }: { isActive: boolean }) {
  return `${NAV_LINK} ${
    isActive
      ? 'bg-[var(--surface-2)] text-[var(--text)]'
      : 'text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]'
  }`
}

export function AppShell() {
  const { user, logout } = useAuth()
  const health = useHealth()
  const fixture = health.data && !health.data.live_mode

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-2 focus:rounded focus:bg-[var(--surface)] focus:p-2"
      >
        Skip to main content
      </a>

      <header className="sticky top-0 z-20 border-b border-[var(--border)] bg-[var(--surface)]/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1440px] items-center gap-2 px-4 sm:px-6">
          <Link
            to="/"
            className="mr-2 flex items-center gap-2 rounded-[var(--radius-sm)] text-[0.9375rem]"
          >
            <LogoMark />
            <Wordmark />
          </Link>

          <nav aria-label="Primary" className="flex items-center gap-1">
            <NavLink to="/" end className={navClass}>
              <FolderIcon />
              <span className="hidden sm:inline">Cases</span>
            </NavLink>
            {canEdit(user) && (
              <NavLink to="/cases/new" className={navClass}>
                <PlusIcon />
                <span className="hidden sm:inline">New case</span>
              </NavLink>
            )}
          </nav>

          <div className="ml-auto flex items-center gap-1">
            <div className="mr-1 hidden items-center gap-2 border-r border-[var(--border)] pr-3 md:flex">
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--surface-2)] text-[var(--muted)]">
                <UserIcon />
              </span>
              <span className="leading-tight">
                <span className="block max-w-40 truncate text-[0.8125rem] font-medium">
                  {user?.full_name}
                </span>
                <span className="text-label block">{user?.role}</span>
              </span>
            </div>
            <ThemeToggle />
            <button
              type="button"
              onClick={() => void logout()}
              aria-label="Sign out"
              className={`${NAV_LINK} text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]`}
            >
              <LogOutIcon />
              <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </div>

        {/* NFR-15: presenting cached data as live, even by omission, is not acceptable. */}
        {fixture && (
          <div
            role="status"
            className="tone-warning border-t border-[var(--warning-border)] px-4 py-1 text-center text-xs font-medium sm:px-6"
          >
            Cached snapshot — not live blockchain data. This instance runs with{' '}
            <code className="font-mono">LIVE_MODE=false</code>; retrieval is served from the
            committed fixture cache.
          </div>
        )}
      </header>

      <main id="main" className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-5 sm:px-6">
        <Outlet />
      </main>
    </div>
  )
}
