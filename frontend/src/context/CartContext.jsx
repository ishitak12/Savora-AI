import { createContext, useCallback, useContext, useMemo, useState } from 'react'

const CartContext = createContext(null)

/**
 * The cart lives in React state only.
 *
 * It holds a display snapshot (name, price, emoji) so the drawer can render
 * without refetching, but checkout sends nothing but ids and quantities —
 * the server re-reads prices and availability. A client that lies about
 * price therefore changes nothing.
 */
export function CartProvider({ children }) {
  const [lines, setLines] = useState([])
  const [open, setOpen] = useState(false)

  const add = useCallback((item, quantity = 1) => {
    setLines((current) => {
      const existing = current.find((l) => l.id === item.id)
      if (existing) {
        return current.map((l) =>
          l.id === item.id ? { ...l, quantity: Math.min(50, l.quantity + quantity) } : l,
        )
      }
      return [
        ...current,
        {
          id: item.id,
          name: item.name,
          price: item.price,
          emoji: item.image_emoji,
          quantity,
        },
      ]
    })
  }, [])

  const setQuantity = useCallback((id, quantity) => {
    setLines((current) =>
      quantity <= 0
        ? current.filter((l) => l.id !== id)
        : current.map((l) => (l.id === id ? { ...l, quantity: Math.min(50, quantity) } : l)),
    )
  }, [])

  const remove = useCallback((id) => {
    setLines((current) => current.filter((l) => l.id !== id))
  }, [])

  const clear = useCallback(() => setLines([]), [])

  const subtotal = useMemo(
    () => lines.reduce((sum, l) => sum + l.price * l.quantity, 0),
    [lines],
  )
  const count = useMemo(() => lines.reduce((sum, l) => sum + l.quantity, 0), [lines])

  const value = useMemo(
    () => ({ lines, add, setQuantity, remove, clear, subtotal, count, open, setOpen }),
    [lines, add, setQuantity, remove, clear, subtotal, count, open],
  )

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>
}

export function useCart() {
  const context = useContext(CartContext)
  if (!context) throw new Error('useCart must be used inside CartProvider')
  return context
}
