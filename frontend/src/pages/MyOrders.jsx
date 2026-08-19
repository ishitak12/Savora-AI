import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import {
  Alert,
  Empty,
  OrderRail,
  Spinner,
  StatusBadge,
  rupees,
  timeAgo,
} from '../components/common'

export default function MyOrders() {
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      setOrders(await api.listOrders())
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  // Poll while the page is open so the customer sees the kitchen move the
  // order along. Polling rather than websockets: one endpoint, no extra
  // infrastructure, and 8 seconds is well inside a diner's patience.
  useEffect(() => {
    load()
    const timer = setInterval(load, 8000)
    return () => clearInterval(timer)
  }, [load])

  if (loading) {
    return (
      <div className="empty">
        <Spinner /> Loading your orders…
      </div>
    )
  }

  return (
    <>
      <div className="section-head">
        <div>
          <h1>Your orders</h1>
          <p>Status updates automatically every few seconds.</p>
        </div>
        <button type="button" className="btn btn-ghost btn-sm" onClick={load}>
          Refresh
        </button>
      </div>

      <Alert>{error}</Alert>

      {orders.length === 0 ? (
        <Empty>You have not placed any orders yet.</Empty>
      ) : (
        orders.map((order) => (
          <article className="card card-pad order-card" key={order.id}>
            <div className="order-head">
              <span className="order-code">{order.order_code}</span>
              <StatusBadge status={order.status} />
              <span className="order-meta">{timeAgo(order.created_at)}</span>
              <span className="price" style={{ marginLeft: 'auto' }}>
                {rupees(order.total_amount)}
              </span>
            </div>

            <div className="order-items">
              {order.items.map((item) => (
                <div key={item.menu_item_id}>
                  {item.quantity} × {item.item_name}
                  <span className="muted"> · {rupees(item.line_total)}</span>
                </div>
              ))}
            </div>

            {order.notes && <p className="small muted">Note: {order.notes}</p>}

            <OrderRail status={order.status} />
          </article>
        ))
      )}
    </>
  )
}
