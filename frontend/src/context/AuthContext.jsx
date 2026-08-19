import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, setToken, getToken } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)

  // On boot, exchange whatever token survived a refresh for the real user
  // record. If it has expired the API says 401 and we land on the login
  // screen — the token is never trusted for its claims alone.
  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      if (!getToken()) {
        setReady(true)
        return
      }
      try {
        const me = await api.me()
        if (!cancelled) setUser(me)
      } catch {
        setToken(null)
      } finally {
        if (!cancelled) setReady(true)
      }
    }
    bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (email, password) => {
    const result = await api.login(email, password)
    setToken(result.access_token)
    setUser(result.user)
    return result.user
  }, [])

  const register = useCallback(async (email, fullName, password) => {
    const result = await api.register(email, fullName, password)
    setToken(result.access_token)
    setUser(result.user)
    return result.user
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, ready, login, register, logout, isAdmin: user?.role === 'admin' }),
    [user, ready, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
