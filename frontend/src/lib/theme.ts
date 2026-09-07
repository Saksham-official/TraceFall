/**
 * Theme preference. Light by default; dark only when the investigator chose it.
 *
 * A display preference, not a credential — localStorage is the right home for it. The
 * OS setting is deliberately ignored: a demo projector's host machine must not decide
 * how the product looks (FRONTEND_SPEC §2).
 */

export type Theme = 'light' | 'dark'

const KEY = 'tracefall.theme'

export function readTheme(): Theme {
  try {
    return localStorage.getItem(KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  if (theme === 'dark') root.setAttribute('data-theme', 'dark')
  else root.removeAttribute('data-theme')
  try {
    if (theme === 'dark') localStorage.setItem(KEY, theme)
    else localStorage.removeItem(KEY)
  } catch {
    // Storage denied — the theme still applies for this page load.
  }
}
