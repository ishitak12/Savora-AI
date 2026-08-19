import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { Alert, Empty, Spinner, TagList, rupees } from '../components/common'

const CATEGORIES = ['Starters', 'Main Course', 'Rice & Biryani', 'Breads', 'Desserts', 'Beverages']
const TAGS = ['vegetarian', 'non-vegetarian', 'spicy', 'vegan', 'contains-nuts']

const SEARCH_STOPWORDS = new Set([
  'a',
  'an',
  'and',
  'any',
  'for',
  'in',
  'is',
  'me',
  'of',
  'on',
  'or',
  'some',
  'something',
  'the',
  'to',
  'want',
  'with',
])

const BLANK = {
  name: '',
  description: '',
  category: 'Main Course',
  price: '',
  tags: [],
  is_available: true,
  image_emoji: '🍽️',
}

function ItemForm({ initial, onSubmit, onCancel, busy }) {
  const [form, setForm] = useState(initial)

  function toggleTag(tag) {
    setForm((f) => ({
      ...f,
      tags: f.tags.includes(tag) ? f.tags.filter((t) => t !== tag) : [...f.tags, tag],
    }))
  }

  return (
    <form
      className="card card-pad mb"
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit({ ...form, price: Number(form.price) })
      }}
    >
      <h3 className="mb">{initial.id ? `Edit “${initial.name}”` : 'Add a menu item'}</h3>

      <div className="field-row">
        <div className="field">
          <label htmlFor="f-name">Name</label>
          <input
            id="f-name"
            className="input"
            required
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </div>
        <div className="field">
          <label htmlFor="f-category">Category</label>
          <select
            id="f-category"
            className="select"
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
          >
            {CATEGORIES.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="field">
        <label htmlFor="f-desc">
          Description <span className="muted">— this text is what the AI search reads</span>
        </label>
        <textarea
          id="f-desc"
          className="textarea"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          placeholder="Describe taste, heat, preparation. Detail here directly improves search quality."
        />
      </div>

      <div className="field-row">
        <div className="field">
          <label htmlFor="f-price">Price (₹)</label>
          <input
            id="f-price"
            className="input"
            type="number"
            min="1"
            step="1"
            required
            value={form.price}
            onChange={(e) => setForm({ ...form, price: e.target.value })}
          />
        </div>
        <div className="field">
          <label htmlFor="f-emoji">Icon</label>
          <input
            id="f-emoji"
            className="input"
            maxLength={4}
            value={form.image_emoji}
            onChange={(e) => setForm({ ...form, image_emoji: e.target.value })}
          />
        </div>
      </div>

      <div className="field">
        <label>Dietary tags</label>
        <div className="checkbox-row">
          {TAGS.map((tag) => (
            <button
              type="button"
              key={tag}
              className="chip-toggle"
              aria-pressed={form.tags.includes(tag)}
              onClick={() => toggleTag(tag)}
            >
              {tag}
            </button>
          ))}
        </div>
      </div>

      <label className="row small">
        <input
          type="checkbox"
          checked={form.is_available}
          onChange={(e) => setForm({ ...form, is_available: e.target.checked })}
        />
        Available to order
      </label>

      <div className="row mt">
        <button className="btn btn-primary" disabled={busy}>
          {busy ? 'Saving…' : initial.id ? 'Save changes' : 'Add item'}
        </button>
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}

function tokenizeFilter(value) {
  return value
    .toLowerCase()
    .split(/[^a-z0-9-]+/)
    .map((part) => part.trim())
    .filter((part) => part && !SEARCH_STOPWORDS.has(part))
}

function matchesFilter(item, filter) {
  const tokens = tokenizeFilter(filter)
  if (tokens.length === 0) return true

  const haystack = [item.name, item.category, item.description, ...(item.tags || [])]
    .join(' ')
    .toLowerCase()

  return tokens.every((token) => haystack.includes(token))
}

export default function AdminMenu({ notify }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(null) // null | BLANK | item
  const [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState('')
  const [previewItem, setPreviewItem] = useState(null)

  const load = useCallback(async () => {
    try {
      setItems(await api.listMenu({ availableOnly: false }))
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function save(form) {
    setBusy(true)
    setError('')
    try {
      if (form.id) {
        await api.updateItem(form.id, {
          name: form.name,
          description: form.description,
          category: form.category,
          price: form.price,
          tags: form.tags,
          is_available: form.is_available,
          image_emoji: form.image_emoji,
        })
        notify(`${form.name} updated`)
      } else {
        await api.createItem(form)
        notify(`${form.name} added to the menu`)
      }
      setEditing(null)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function toggle(item) {
    try {
      await api.toggleAvailability(item.id)
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  async function remove(item) {
    try {
      await api.deleteItem(item.id)
      notify(`${item.name} removed`)
      await load()
    } catch (err) {
      // 409 here means the dish appears on a past order; the backend tells
      // the admin to mark it unavailable instead of deleting history.
      setError(err.message)
    }
  }

  const visible = items.filter((item) => matchesFilter(item, filter))

  if (loading) {
    return (
      <div className="empty">
        <Spinner /> Loading the menu…
      </div>
    )
  }

  return (
    <>
      <div className="section-head">
        <div>
          <h1>Menu management</h1>
          <p>
            {items.length} items · {items.filter((i) => i.is_available).length} available
          </p>
        </div>
        {!editing && (
          <button type="button" className="btn btn-primary" onClick={() => setEditing({ ...BLANK })}>
            + Add item
          </button>
        )}
      </div>

      <Alert>{error}</Alert>

      {editing && (
        <ItemForm
          initial={editing}
          onSubmit={save}
          onCancel={() => setEditing(null)}
          busy={busy}
        />
      )}

      <div className="filter-row">
        <input
          className="input"
          style={{ maxWidth: 320 }}
          placeholder="Filter by name, category, tags, or description"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setFilter('')}>
          Clear filter
        </button>
      </div>

      {visible.length === 0 ? (
        <Empty>No items match that filter.</Empty>
      ) : (
        <div className="admin-menu-grid">
          {visible.map((item) => (
            <article
              key={item.id}
              className={`card card-pad admin-menu-card ${item.is_available ? '' : 'dish-unavailable'}`}
              role="button"
              tabIndex={0}
              onClick={() => setPreviewItem(item)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  setPreviewItem(item)
                }
              }}
            >
              <div className="admin-menu-head">
                <div className="row" style={{ gap: '0.55rem' }}>
                  <span aria-hidden="true" className="dish-emoji admin-emoji">
                    {item.image_emoji}
                  </span>
                  <div>
                    <div className="admin-menu-name">{item.name}</div>
                    <div className="muted small">{item.category}</div>
                  </div>
                </div>
                <span className={`mode-badge ${item.is_available ? 'live' : 'degraded'}`}>
                  {item.is_available ? 'Available' : 'Unavailable'}
                </span>
              </div>

              <p className="admin-menu-desc">{item.description}</p>

              <TagList tags={item.tags} />

              <div className="admin-menu-foot">
                <strong>{rupees(item.price)}</strong>
                <div className="row" style={{ gap: '0.35rem' }}>
                  <button
                    type="button"
                    className="chip-toggle"
                    aria-pressed={item.is_available}
                    onClick={(e) => {
                      e.stopPropagation()
                      toggle(item)
                    }}
                  >
                    Toggle
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm btn-ghost"
                    onClick={(e) => {
                      e.stopPropagation()
                      setEditing({ ...item, price: String(item.price) })
                    }}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm btn-danger"
                    onClick={(e) => {
                      e.stopPropagation()
                      remove(item)
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}

      {previewItem && (
        <div className="modal-backdrop" onClick={() => setPreviewItem(null)}>
          <aside className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div className="row" style={{ gap: '0.75rem' }}>
                <span aria-hidden="true" className="dish-emoji">
                  {previewItem.image_emoji}
                </span>
                <div>
                  <h3>{previewItem.name}</h3>
                  <p className="muted small">{previewItem.category}</p>
                </div>
              </div>
              <button type="button" className="btn btn-sm btn-ghost" onClick={() => setPreviewItem(null)}>
                Close
              </button>
            </div>

            <p className="modal-desc">{previewItem.description}</p>
            <div className="modal-tags">
              <TagList tags={previewItem.tags} />
            </div>

            <div className="modal-foot">
              <span className={`mode-badge ${previewItem.is_available ? 'live' : 'degraded'}`}>
                {previewItem.is_available ? 'Live on menu' : 'Hidden from menu'}
              </span>
              <div className="row" style={{ gap: '0.4rem' }}>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => {
                    setEditing({ ...previewItem, price: String(previewItem.price) })
                    setPreviewItem(null)
                  }}
                >
                  Edit item
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => {
                    toggle(previewItem)
                    setPreviewItem(null)
                  }}
                >
                  {previewItem.is_available ? 'Mark unavailable' : 'Mark available'}
                </button>
              </div>
            </div>
          </aside>
        </div>
      )}
    </>
  )
}
