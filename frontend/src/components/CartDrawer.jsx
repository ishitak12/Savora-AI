import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useCart } from '../context/CartContext'
import { useAuth } from '../context/AuthContext'
import { Alert, rupees } from './common'

export default function CartDrawer({ notify }) {
  const { lines, setQuantity, remove, clear, subtotal, count, open, setOpen } = useCart()
  const { user } = useAuth()
  const navigate = useNavigate()

  const [notes, setNotes] = useState('')
  const [error, setError] = useState('')
  const [placing, setPlacing] = useState(false)

  async function checkout() {
    setError('')
    setPlacing(true)
    try {
      const order = await api.placeOrder(
        lines.map((l) => ({ menu_item_id: l.id, quantity: l.quantity })),
        notes,
      )
      clear()
      setNotes('')
      setOpen(false)
      notify(`Order ${order.order_code} placed`)
      navigate('/orders')
    } catch (err) {
      // The most interesting failure here is 409: the admin turned an item
      // off while it sat in the cart. Surfacing the backend's message tells
      // the customer exactly which dish to drop.
      setError(err.message)
    } finally {
      setPlacing(false)
    }
  }

  if (!open) {
    return count > 0 ? (
      <button type="button" className="cart-fab" onClick={() => setOpen(true)}>
        🛒 {count} item{count > 1 ? 's' : ''} · {rupees(subtotal)}
      </button>
    ) : null
  }

  return (
    <>
      <div className="cart-backdrop" onClick={() => setOpen(false)} />
      <aside className="cart-panel" aria-label="Cart">
        <div className="cart-head">
          <h2>Your cart</h2>
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            style={{ marginLeft: 'auto' }}
            onClick={() => setOpen(false)}
          >
            Close
          </button>
        </div>

        <div className="cart-body">
          {lines.length === 0 ? (
            <p className="muted small mt">Your cart is empty.</p>
          ) : (
            lines.map((line) => (
              <div className="cart-line" key={line.id}>
                <span aria-hidden="true">{line.emoji}</span>
                <div className="cart-line-name">
                  {line.name}
                  <div className="muted small">{rupees(line.price)} each</div>
                </div>
                <div className="qty">
                  <button
                    type="button"
                    onClick={() => setQuantity(line.id, line.quantity - 1)}
                    aria-label={`Reduce ${line.name}`}
                  >
                    −
                  </button>
                  <span>{line.quantity}</span>
                  <button
                    type="button"
                    onClick={() => setQuantity(line.id, line.quantity + 1)}
                    aria-label={`Add ${line.name}`}
                  >
                    +
                  </button>
                </div>
                <span className="price small">{rupees(line.price * line.quantity)}</span>
                <button
                  type="button"
                  className="btn btn-sm btn-ghost"
                  onClick={() => remove(line.id)}
                  aria-label={`Remove ${line.name}`}
                >
                  ×
                </button>
              </div>
            ))
          )}
        </div>

        <div className="cart-foot">
          <Alert>{error}</Alert>

          {lines.length > 0 && (
            <>
              <div className="field">
                <label htmlFor="notes">Notes for the kitchen (optional)</label>
                <textarea
                  id="notes"
                  className="textarea"
                  value={notes}
                  maxLength={500}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Less oil, pack cutlery…"
                />
              </div>
              <div className="total-row">
                <span className="muted">Items</span>
                <span>{count}</span>
              </div>
              <div className="total-row grand">
                <span>Total</span>
                <span>{rupees(subtotal)}</span>
              </div>
            </>
          )}

          <button
            type="button"
            className="btn btn-primary btn-block mt"
            disabled={lines.length === 0 || placing || !user}
            onClick={checkout}
          >
            {placing ? 'Placing order…' : user ? 'Place order' : 'Sign in to order'}
          </button>
        </div>
      </aside>
    </>
  )
}
