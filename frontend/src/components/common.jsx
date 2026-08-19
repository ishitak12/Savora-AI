import { useEffect } from 'react'

export const WORKFLOW = ['Placed', 'Confirmed', 'Preparing', 'Ready', 'Picked Up']

/** Ordinal ramp — index maps to the stage's position in the workflow. */
export const STAGE_COLOR = {
  Placed: 'var(--stage-1)',
  Confirmed: 'var(--stage-2)',
  Preparing: 'var(--stage-3)',
  Ready: 'var(--stage-4)',
  'Picked Up': 'var(--stage-5)',
  Cancelled: 'var(--stage-cancelled)',
}

export function rupees(value) {
  return `₹${Number(value ?? 0).toLocaleString('en-IN', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}`
}

export function timeAgo(iso) {
  if (!iso) return ''
  const then = new Date(iso.endsWith('Z') ? iso : `${iso}Z`)
  const minutes = Math.max(0, Math.round((Date.now() - then.getTime()) / 60000))
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return then.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

export function StatusBadge({ status }) {
  return (
    <span className="status-badge">
      <span className="status-dot" style={{ background: STAGE_COLOR[status] }} />
      {status}
    </span>
  )
}

export function TagList({ tags = [] }) {
  const className = (tag) =>
    tag === 'vegetarian' || tag === 'vegan'
      ? 'tag tag-veg'
      : tag === 'non-vegetarian'
        ? 'tag tag-nonveg'
        : tag === 'spicy'
          ? 'tag tag-spicy'
          : 'tag'
  return (
    <div className="tags">
      {tags.map((tag) => (
        <span key={tag} className={className(tag)}>
          {tag === 'spicy' ? '🌶 spicy' : tag}
        </span>
      ))}
    </div>
  )
}

export function Alert({ kind = 'error', children }) {
  if (!children) return null
  return <div className={`alert alert-${kind}`}>{children}</div>
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>
}

export function Spinner() {
  return <span className="spinner" aria-label="Loading" />
}

export function Toast({ message, onDone }) {
  useEffect(() => {
    if (!message) return undefined
    const timer = setTimeout(onDone, 2600)
    return () => clearTimeout(timer)
  }, [message, onDone])
  if (!message) return null
  return (
    <div className="toast" role="status">
      {message}
    </div>
  )
}

/** Progress rail shown on a customer's order card. */
export function OrderRail({ status }) {
  if (status === 'Cancelled') {
    return <p className="small muted mt">This order was cancelled.</p>
  }
  const currentIndex = WORKFLOW.indexOf(status)
  return (
    <div>
      <div className="rail">
        {WORKFLOW.map((stage, index) => (
          <div className="rail-step" key={stage}>
            <span
              className={`rail-node ${
                index < currentIndex ? 'done' : index === currentIndex ? 'current' : ''
              }`}
            />
            {index < WORKFLOW.length - 1 && (
              <span className={`rail-line ${index < currentIndex ? 'done' : ''}`} />
            )}
          </div>
        ))}
      </div>
      <div className="rail-labels">
        {WORKFLOW.map((stage) => (
          <span key={stage}>{stage}</span>
        ))}
      </div>
    </div>
  )
}
