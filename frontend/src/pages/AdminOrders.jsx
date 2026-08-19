import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import {
  Alert,
  Empty,
  OrderRail,
  Spinner,
  StatusBadge,
  WORKFLOW,
  rupees,
  timeAgo,
} from '../components/common'

const FILTERS = ['Active', 'All', ...WORKFLOW, 'Cancelled']

function formatOrderLabel(orderCode) {
  return orderCode
}

export default function AdminOrders({ notify }) {
  const [orders, setOrders] = useState([])
  const [filter, setFilter] = useState('Active')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState(null)
  const [expanded, setExpanded] = useState(null)

  const load = useCallback(async () => {
    try {
      const params =
        filter === 'Active'
          ? { activeOnly: true }
          : filter === 'All'
            ? {}
            : { status: filter }
      setOrders(await api.listOrders(params))
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => {
    load()
    const timer = setInterval(load, 8000)
    return () => clearInterval(timer)
  }, [load])

  async function advance(order, status) {
    setBusyId(order.id)
    setError('')
    try {
      await api.updateOrderStatus(order.id, status)
      notify(`${formatOrderLabel(order.order_code)} → ${status}`)
      await load()
    } catch (err) {
      // The backend owns the state machine. If the UI offers an illegal
      // transition because another admin moved the order first, the 422
      // message explains exactly what happened.
      setError(err.message)
      await load()
    } finally {
      setBusyId(null)
    }
  }

  function toggleExpanded(id) {
    setExpanded((current) => (current === id ? null : id))
  }

  return (
    <>
      <div className="section-head">
        <div>
          <h1>Incoming orders</h1>
          <p>Refreshes every 8 seconds. Transitions are validated server-side.</p>
        </div>
        <button type="button" className="btn btn-ghost btn-sm" onClick={load}>
          Refresh
        </button>
      </div>

      <div className="filter-row">
        {FILTERS.map((f) => (
          <button
            key={f}
            className="chip-toggle"
            aria-pressed={filter === f}
            onClick={() => setFilter(f)}
          >
            {f}
          </button>
        ))}
      </div>

      <Alert>{error}</Alert>

      {loading ? (
        <div className="empty">
          <Spinner /> Loading orders…
        </div>
      ) : orders.length === 0 ? (
        <Empty>No orders in this view.</Empty>
      ) : (
        orders.map((order) => (
          <article className="card card-pad order-card order-card-interactive" key={order.id}>
            <button
              className="order-summary"
              type="button"
              title={order.order_code}
              onClick={() => toggleExpanded(order.id)}
            >
              <div className="order-head order-head-top">
                <div className="order-title-block">
                  <span className="order-code">{formatOrderLabel(order.order_code)}</span>
                </div>
                <StatusBadge status={order.status} />
                <span className="order-meta order-time">{timeAgo(order.created_at)}</span>
                <span className="price order-total">{rupees(order.total_amount)}</span>
              </div>
            </button>

            {expanded === order.id && (
              <div className="order-expanded">
                <div className="order-items order-items-list">
                  {order.items.map((item) => (
                    <div key={item.menu_item_id} className="order-item-line">
                      <span>{item.quantity} × {item.item_name}</span>
                      <span className="muted small">· {rupees(item.line_total)}</span>
                    </div>
                  ))}
                </div>

                <OrderRail status={order.status} />

                {order.notes && <p className="small muted">Note: {order.notes}</p>}

                <div className="order-actions">
                  {order.allowed_transitions.length === 0 ? (
                    <span className="small muted">No further action — {order.status.toLowerCase()}.</span>
                  ) : (
                    order.allowed_transitions.map((status) => (
                      <button
                        key={status}
                        className={`btn btn-sm ${status === 'Cancelled' ? 'btn-danger' : 'btn-primary'}`}
                        disabled={busyId === order.id}
                        onClick={() => advance(order, status)}
                      >
                        {status === 'Cancelled' ? 'Cancel' : `Mark ${status}`}
                      </button>
                    ))
                  )}
                </div>
              </div>
            )}
          </article>
        ))
      )}
    </>
  )
}
