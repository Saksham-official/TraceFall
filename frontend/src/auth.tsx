/** Session state. Tokens live in `api/client`; this holds only the current user. */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { clearTokens, request, setSessionExpiredHandler, setTokens } from './api/client'
import type { TokenResponse, User } from './api/types'

interface AuthValue {
  user: User | null
  /** True when the session ended on its own — shown on the login screen. */
  sessionExpired: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [sessionExpired, setSessionExpired] = useState(false)

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
    () => ({ user, sessionExpired, login, logout }),
    [user, sessionExpired, login, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const location = useLocation()
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  return <>{children}</>
}

/** Case mutations are INVESTIGATOR+ on the backend; VIEWER sees read-only affordances. */
export function canEdit(user: User | null): boolean {
  return user !== null && user.role !== 'VIEWER'
}
