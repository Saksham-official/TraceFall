import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import axe from 'axe-core'
import type { ReactElement, ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'

import { clearTokens } from '../api/client'
import { AuthProvider } from '../auth'

export interface StubRoute {
  /** Matched against `${method} ${path}`, e.g. 'POST /api/v1/auth/login'. */
  match: string
  status?: number
  body?: unknown
}

/** Routes fetch by method and path; an unmatched call fails the test loudly. */
export function stubFetch(routes: StubRoute[]) {
  const calls: { url: string; method: string; body: unknown }[] = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    calls.push({
      url,
      method,
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : undefined,
    })
    const route = routes.find((candidate) => candidate.match === `${method} ${url}`)
    if (!route) throw new Error(`Unstubbed request: ${method} ${url}`)
    const status = route.status ?? 200
    return new Response(route.body === undefined ? null : JSON.stringify(route.body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return calls
}

export function apiError(code: string, message: string, field?: string) {
  return { error: { code, message, field, request_id: 'test-request' } }
}

function Providers({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <QueryClientProvider client={client}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  )
}

export function renderWithProviders(
  ui: ReactElement,
  options: { path?: string; route?: string } = {},
) {
  clearTokens()
  const { path = '/', route = path } = options
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Providers>
        <Routes>
          <Route path={path} element={ui} />
        </Routes>
      </Providers>
    </MemoryRouter>,
  )
}

export function renderApp(app: ReactElement, route = '/') {
  clearTokens()
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Providers>{app}</Providers>
    </MemoryRouter>,
  )
}

/**
 * Fails on any axe violation. `color-contrast` is off because jsdom has no layout or canvas
 * to sample pixels from — contrast is enforced by the token palette instead.
 */
export async function expectNoAxeViolations(container: HTMLElement) {
  const results = await axe.run(container, {
    resultTypes: ['violations'],
    rules: { 'color-contrast': { enabled: false } },
  })
  const described = results.violations.map((v) => `${v.id}: ${v.help}`)
  if (described.length > 0) throw new Error(`axe violations:\n${described.join('\n')}`)
}
