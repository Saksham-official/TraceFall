/**
 * HTTP client and token store.
 *
 * Tokens are held in module memory only — never localStorage, sessionStorage, or a
 * cookie readable by script, so an XSS cannot exfiltrate a session.
 *
 * The refresh token is *also* held in memory, but it is not the only copy: the backend
 * issues it as an httpOnly cookie scoped to the auth routes, which script cannot read and
 * so cannot exfiltrate. That cookie is what survives a page reload — `restoreSession()`
 * calls `POST /auth/refresh` with no body at all and the browser supplies it.
 *
 * Every request sends `credentials: 'include'` so the cookie travels on the one route
 * that needs it.
 */

import type { ApiErrorBody, TokenResponse } from './types'

const BASE = '/api/v1'

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: ApiErrorBody,
  ) {
    super(body.message)
    this.name = 'ApiError'
  }

  get code(): string {
    return this.body.code
  }

  get field(): string | undefined {
    return this.body.field
  }
}

let accessToken: string | null = null
let refreshToken: string | null = null
let refreshInFlight: Promise<boolean> | null = null
let onSessionExpired: (() => void) | null = null

export function setTokens(tokens: Pick<TokenResponse, 'access_token' | 'refresh_token'>): void {
  accessToken = tokens.access_token
  refreshToken = tokens.refresh_token
}

export function clearTokens(): void {
  accessToken = null
  refreshToken = null
  refreshInFlight = null
}

export function hasSession(): boolean {
  return accessToken !== null
}

/** Called when a session ends without the user asking — expired or revoked refresh. */
export function setSessionExpiredHandler(handler: (() => void) | null): void {
  onSessionExpired = handler
}

async function parse(response: Response): Promise<unknown> {
  if (response.status === 204) return null
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

function toApiError(status: number, payload: unknown): ApiError {
  const error = (payload as { error?: Partial<ApiErrorBody> } | null)?.error
  return new ApiError(status, {
    code: error?.code ?? 'INTERNAL_ERROR',
    message: error?.message ?? 'Something went wrong. Please try again.',
    field: error?.field,
    request_id: error?.request_id ?? '-',
  })
}

interface RequestOptions {
  method?: string
  body?: unknown
  /** Auth endpoints must not trigger the refresh-and-retry loop. */
  skipAuthRetry?: boolean
  signal?: AbortSignal
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = {}
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`

  return fetch(`${BASE}${path}`, {
    method: options.method ?? 'GET',
    headers,
    credentials: 'include',
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  })
}

async function refreshSession(): Promise<boolean> {
  refreshInFlight ??= (async () => {
    // The body carries the in-memory token when there is one, for a client with no
    // cookie jar. With none, the httpOnly cookie alone is enough — which is exactly the
    // page-reload case.
    const response = await send('/auth/refresh', {
      method: 'POST',
      body: refreshToken ? { refresh_token: refreshToken } : {},
      skipAuthRetry: true,
    })
    if (!response.ok) return false
    setTokens((await parse(response)) as TokenResponse)
    return true
  })()
    .catch(() => false)
    .finally(() => {
      refreshInFlight = null
    })
  return refreshInFlight
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response = await send(path, options)

  if (response.status === 401 && !options.skipAuthRetry) {
    if (await refreshSession()) {
      response = await send(path, options)
    } else {
      clearTokens()
      onSessionExpired?.()
    }
  }

  const payload = await parse(response)
  if (!response.ok) throw toApiError(response.status, payload)
  return payload as T
}

/**
 * Rebuild a session from the httpOnly refresh cookie, if the browser still holds one.
 *
 * Called once at start-up. Returns the signed-in user, or null when there is no cookie,
 * it has expired, or it has been revoked — all of which are the ordinary "please sign in"
 * case rather than an error worth showing.
 */
export async function restoreSession(): Promise<TokenResponse['user'] | null> {
  const response = await send('/auth/refresh', {
    method: 'POST',
    body: {},
    skipAuthRetry: true,
  })
  if (!response.ok) return null
  const tokens = (await parse(response)) as TokenResponse
  setTokens(tokens)
  return tokens.user
}

export function query(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ''
}
