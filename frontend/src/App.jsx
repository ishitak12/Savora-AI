import { useCallback, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { CartProvider, useCart } from './context/CartContext'
import CartDrawer from './components/CartDrawer'
import { Spinner, Toast } from './components/common'
import Login from './pages/Login'
import CustomerMenu from './pages/CustomerMenu'
import MyOrders from './pages/MyOrders'
import AdminMenu from './pages/AdminMenu'
import AdminOrders from './pages/AdminOrders'
import AdminDashboard from './pages/AdminDashboard'

function Header() {
  const { user, isAdmin, logout } = useAuth()
  const { count, setOpen } = useCart()
  const navigate = useNavigate()

  return (
    <header className="header">
      <div className="header-inner">
        <NavLink to={isAdmin ? '/admin' : '/'} className="brand">
          <span className="brand-mark">S</span>
          Savora
        </NavLink>

        <nav className="nav">
          {isAdmin ? (
            <>
              <NavLink to="/admin" end>
                Dashboard
              </NavLink>
              <NavLink to="/admin/orders">Orders</NavLink>
              <NavLink to="/admin/menu">Menu</NavLink>
            </>
          ) : (
            <>
              <NavLink to="/" end>
                Menu
              </NavLink>
              <NavLink to="/orders">My orders</NavLink>
            </>
          )}
        </nav>

        <div className="header-right">
          {!isAdmin && (
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => setOpen(true)}>
              🛒 {count}
            </button>
          )}
          <div className="user-chip">
            <strong>{user.full_name}</strong>
            <span>{user.role}</span>
          </div>
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={() => {
              logout()
              navigate('/login', { replace: true })
            }}
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  )
}

/** Route guard. `role` narrows to one role; omit it for any signed-in user. */
function Protected({ role, children }) {
  const { user, ready } = useAuth()
  if (!ready) {
    return (
      <div className="empty" style={{ margin: '4rem auto', maxWidth: 320 }}>
        <Spinner /> Loading…
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  if (role && user.role !== role) {
    return <Navigate to={user.role === 'admin' ? '/admin' : '/'} replace />
  }
  return children
}

function Shell({ children, notify }) {
  const { isAdmin } = useAuth()
  return (
    <div className="app-shell">
      <Header />
      <main className="page">{children}</main>
      {!isAdmin && <CartDrawer notify={notify} />}
    </div>
  )
}

function Router() {
  const [toast, setToast] = useState('')
  const notify = useCallback((message) => setToast(message), [])
  const clearToast = useCallback(() => setToast(''), [])

  return (
    <>
      <Routes>
        <Route path="/login" element={<Login />} />

        <Route
          path="/"
          element={
            <Protected role="customer">
              <Shell notify={notify}>
                <CustomerMenu notify={notify} />
              </Shell>
            </Protected>
          }
        />
        <Route
          path="/orders"
          element={
            <Protected role="customer">
              <Shell notify={notify}>
                <MyOrders />
              </Shell>
            </Protected>
          }
        />

        <Route
          path="/admin"
          element={
            <Protected role="admin">
              <Shell notify={notify}>
                <AdminDashboard />
              </Shell>
            </Protected>
          }
        />
        <Route
          path="/admin/orders"
          element={
            <Protected role="admin">
              <Shell notify={notify}>
                <AdminOrders notify={notify} />
              </Shell>
            </Protected>
          }
        />
        <Route
          path="/admin/menu"
          element={
            <Protected role="admin">
              <Shell notify={notify}>
                <AdminMenu notify={notify} />
              </Shell>
            </Protected>
          }
        />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      <Toast message={toast} onDone={clearToast} />
    </>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <CartProvider>
        <Router />
      </CartProvider>
    </AuthProvider>
  )
}
