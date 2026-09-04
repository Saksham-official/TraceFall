/**
 * HTTP client and token store.
 *
 * Tokens are held in module memory only — never localStorage, sessionStorage, or a
 * cookie readable by script, so an XSS cannot exfiltrate a session.
 *
 * The refresh token is *also* in memory, which means a page reload ends the session.
 * That is deliberate: `POST /auth/refresh` currently takes the refresh token in the
 * request body and sets no cookie, so there is no httpOnly cookie to fall back on.
 * `credentials: 'include'` is set on every request so that when the backend starts
 * issuing the refresh token as an httpOnly cookie, reload-survival needs no change here.
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
  if (!refreshToken) return false
  refreshInFlight ??= (async () => {
    const response = await send('/auth/refresh', {
      method: 'POST',
      body: { refresh_token: refreshToken },
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

export function query(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ''
}
