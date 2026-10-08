import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ApiError, setUnauthorizedHandler } from '../api/client'
import * as authApi from '../api/auth'
import type { SessionUser } from '../types'
import { mapApiUser } from '../types'

interface AuthContextValue {
  user: SessionUser | null
  bootstrapping: boolean
  signIn: (identifier: string, password: string) => Promise<string | null>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null)
  const [bootstrapping, setBootstrapping] = useState(true)

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
    return () => setUnauthorizedHandler(null)
  }, [])

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const me = await authApi.getMe()
        if (!active) return
        setUser(me.authenticated && me.user ? mapApiUser(me.user) : null)
      } catch {
        if (active) setUser(null)
      } finally {
        if (active) setBootstrapping(false)
      }
    })()
    return () => {
      active = false
    }
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      bootstrapping,
      signIn: async (identifier, password) => {
        if (!identifier.trim()) return 'Enter your username or email.'
        if (password.trim().length < 6) return 'Password must be at least 6 characters.'
        try {
          const result = await authApi.login(identifier.trim(), password)
          setUser(mapApiUser(result.user))
          return null
        } catch (error) {
          if (error instanceof ApiError) {
            if (error.status === 401) return 'Invalid username/email or password.'
            return error.detail || error.message || 'Unable to sign in.'
          }
          return 'Unable to reach the API. Check VITE_API_BASE_URL and the API host.'
        }
      },
      signOut: async () => {
        try {
          await authApi.logout()
        } catch {
          // Clear local session even if logout request fails.
        }
        setUser(null)
      },
    }),
    [user, bootstrapping],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
