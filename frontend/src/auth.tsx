/** Session state. Tokens live in `api/client`; this holds only the current user. */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import {
  clearTokens,
  request,
  restoreSession,
  setSessionExpiredHandler,
  setTokens,
} from './api/client'
import type { TokenResponse, User } from './api/types'
import { Spinner } from './components/ui'

interface AuthValue {
  user: User | null
  /** True until the start-up session restore has finished, so routes do not flash. */
  restoring: boolean
  /** True when the session ended on its own — shown on the login screen. */
  sessionExpired: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [sessionExpired, setSessionExpired] = useState(false)
  const [restoring, setRestoring] = useState(true)

  // A reload loses the in-memory tokens but not the httpOnly refresh cookie, so the
  // session can be rebuilt from it. Without this, pasting a workspace URL into a new tab
  // always lands on the sign-in screen.
  useEffect(() => {
    let cancelled = false
    void restoreSession()
      .then((restored) => {
        if (!cancelled && restored) setUser(restored)
      })
      .finally(() => {
        if (!cancelled) setRestoring(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    setSessionExpiredHandler(() => {
      setUser(null)
      setSessionExpired(true)
    })
    return () => setSessionExpiredHandler(null)
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: { email, password },
      skipAuthRetry: true,
    })
    setTokens(tokens)
    setSessionExpired(false)
    setUser(tokens.user)
  }, [])

  const logout = useCallback(async () => {
    try {
      await request<null>('/auth/logout', { method: 'POST', skipAuthRetry: true })
    } catch {
      // The server-side revoke failed, but the local session must still end.
    } finally {
      clearTokens()
      setSessionExpired(false)
      setUser(null)
    }
  }, [])

  const value = useMemo(
    () => ({ user, restoring, sessionExpired, login, logout }),
    [user, restoring, sessionExpired, login, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, restoring } = useAuth()
  const location = useLocation()
  // Redirecting mid-restore would bounce a reloading user to the sign-in screen and
  // discard where they were going.
  if (restoring) return <Spinner label="Restoring session" />
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  return <>{children}</>
}

/** Case mutations are INVESTIGATOR+ on the backend; VIEWER sees read-only affordances. */
export function canEdit(user: User | null): boolean {
  return user !== null && user.role !== 'VIEWER'
}
