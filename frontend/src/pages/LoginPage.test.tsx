import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from '../App'
import { apiError, renderApp, stubFetch } from '../test/utils'

const USER = {
  id: 1,
  email: 'inspector@example.gov.in',
  full_name: 'R. Khooda',
  role: 'INVESTIGATOR',
  organisation: 'Cyber Cell',
  last_login_at: null,
}

const TOKENS = {
  access_token: 'access-1',
  refresh_token: 'refresh-1',
  token_type: 'bearer',
  expires_in: 900,
  user: USER,
}

const HEALTH = {
  match: 'GET /api/v1/health',
  body: { status: 'ok', version: '0.1.0', live_mode: false, queue_reachable: true, providers: [] },
}

const EMPTY_CASES = {
  match: 'GET /api/v1/cases',
  body: { items: [], next_cursor: null, has_more: false },
}

async function signIn() {
  await screen.findByLabelText(/password/i)
  fireEvent.change(screen.getByLabelText(/email/i), { target: { value: USER.email } })
  fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'correct horse' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
}

afterEach(() => vi.unstubAllGlobals())

describe('login and protected routes', () => {
  it('sends an unauthenticated visitor to the sign-in screen', async () => {
    stubFetch([])
    renderApp(<App />, '/cases/new')
    // Start-up first asks whether an httpOnly refresh cookie can restore a session; the
    // sign-in screen appears once that answer is no.
    expect(await screen.findByRole('heading', { name: 'TraceFall' })).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
  })

  it('signs in, lands on the dashboard, and keeps no token in web storage', async () => {
    const calls = stubFetch([
      { match: 'POST /api/v1/auth/login', body: TOKENS },
      HEALTH,
      EMPTY_CASES,
    ])
    renderApp(<App />, '/')
    await signIn()

    expect(await screen.findByRole('heading', { name: 'Cases' })).toBeInTheDocument()
    expect(JSON.stringify(localStorage)).not.toContain('access-1')
    expect(JSON.stringify(sessionStorage)).not.toContain('refresh-1')

    const cases = calls.find((call) => call.url === '/api/v1/cases')
    expect(cases).toBeDefined()
  })

  it('shows the backend message on bad credentials without saying which field was wrong', async () => {
    stubFetch([
      {
        match: 'POST /api/v1/auth/login',
        status: 401,
        body: apiError('UNAUTHENTICATED', 'Incorrect email or password'),
      },
    ])
    renderApp(<App />, '/')
    await signIn()

    expect(await screen.findByText('Incorrect email or password')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Cases' })).not.toBeInTheDocument()
  })

  it('returns to sign-in with an explanation when the session can no longer be refreshed', async () => {
    stubFetch([
      { match: 'POST /api/v1/auth/login', body: TOKENS },
      HEALTH,
      {
        match: 'GET /api/v1/cases',
        status: 401,
        body: apiError('UNAUTHENTICATED', 'Authentication required'),
      },
      {
        match: 'POST /api/v1/auth/refresh',
        status: 401,
        body: apiError('UNAUTHENTICATED', 'Refresh token has been revoked'),
      },
    ])
    renderApp(<App />, '/')
    await signIn()

    await waitFor(() => expect(screen.getByText('Your session expired')).toBeInTheDocument())
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
  })

  it('restores a session from the httpOnly refresh cookie on reload', async () => {
    // The in-memory tokens are gone after a reload; the cookie is not, and the browser
    // sends it. Without this, pasting a case URL into a new tab always lands on sign-in.
    stubFetch([
      { match: 'POST /api/v1/auth/refresh', body: TOKENS },
      HEALTH,
      EMPTY_CASES,
    ])

    renderApp(<App />, '/')

    expect(await screen.findByRole('heading', { name: 'Cases' })).toBeInTheDocument()
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument()
  })

  it('keeps the restored session out of web storage too', async () => {
    stubFetch([
      { match: 'POST /api/v1/auth/refresh', body: TOKENS },
      HEALTH,
      EMPTY_CASES,
    ])

    renderApp(<App />, '/')
    await screen.findByRole('heading', { name: 'Cases' })

    // The whole point of the httpOnly cookie is that script never holds the credential.
    expect(JSON.stringify(localStorage)).not.toContain('refresh-1')
    expect(JSON.stringify(sessionStorage)).not.toContain('refresh-1')
    expect(document.cookie).not.toContain('refresh-1')
  })

  it('signs out on request and revokes the refresh token server-side', async () => {
    const calls = stubFetch([
      { match: 'POST /api/v1/auth/login', body: TOKENS },
      HEALTH,
      EMPTY_CASES,
      { match: 'POST /api/v1/auth/logout', status: 204 },
    ])
    renderApp(<App />, '/')
    await signIn()
    await screen.findByRole('heading', { name: 'Cases' })

    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    await waitFor(() => expect(screen.getByLabelText(/password/i)).toBeInTheDocument())
    expect(calls.some((call) => call.url === '/api/v1/auth/logout')).toBe(true)
  })
})
