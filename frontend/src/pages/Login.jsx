import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Alert } from '../components/common'

export default function Login() {
  const { login, register } = useAuth()
  const navigate = useNavigate()

  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      const user =
        mode === 'login'
          ? await login(email, password)
          : await register(email, fullName, password)
      navigate(user.role === 'admin' ? '/admin' : '/', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  function fill(as) {
    setMode('login')
    setEmail(as === 'admin' ? 'admin@savora.in' : 'customer@savora.in')
    setPassword(as === 'admin' ? 'admin123' : 'customer123')
    setError('')
  }

  return (
    <div className="login-wrap">
      <div className="card card-pad login-card">
        <div className="brand mb">
          <span className="brand-mark">S</span>
          Savora
        </div>
        <h1>{mode === 'login' ? 'Sign in' : 'Create an account'}</h1>
        <p className="muted small mb">
          {mode === 'login'
            ? 'Order food, or manage the kitchen.'
            : 'New accounts are customer accounts.'}
        </p>

        <Alert>{error}</Alert>

        <form onSubmit={submit}>
          {mode === 'register' && (
            <div className="field">
              <label htmlFor="name">Full name</label>
              <input
                id="name"
                className="input"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                autoComplete="name"
              />
            </div>
          )}
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              className="input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            />
          </div>
          <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
            {busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>

        <p className="small mt">
          {mode === 'login' ? "Don't have an account? " : 'Already registered? '}
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={() => {
              setMode(mode === 'login' ? 'register' : 'login')
              setError('')
            }}
          >
            {mode === 'login' ? 'Register' : 'Sign in'}
          </button>
        </p>

        <div className="demo-creds">
          <strong>Demo accounts</strong>
          <div className="row" style={{ marginTop: '0.4rem' }}>
            <button type="button" className="btn btn-sm" onClick={() => fill('admin')}>
              Admin
            </button>
            <button type="button" className="btn btn-sm" onClick={() => fill('customer')}>
              Customer
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
