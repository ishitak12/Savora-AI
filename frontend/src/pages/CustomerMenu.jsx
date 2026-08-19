import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { useCart } from '../context/CartContext'
import { Alert, Empty, Spinner, TagList, rupees } from '../components/common'

const SUGGESTIONS = [
  'something spicy and vegetarian under 200 rupees',
  'a light lunch that is not fried',
  'rich and comforting for a cold evening',
  'a dessert without nuts',
  'high protein non veg, no gravy',
]

function Dish({ item, onAdd, matchScore, reason }) {
  return (
    <article className="dish dish-clickable">
      <div className="dish-top">
        <span className="dish-emoji" aria-hidden="true">
          {item.image_emoji}
        </span>
        <div className="grow">
          <div className="dish-name">{item.name}</div>
          <div className="muted small">{item.category}</div>
        </div>
      </div>
      <p className="dish-desc">{item.description}</p>
      <TagList tags={item.tags} />

      {matchScore !== undefined && (
        <div className="match-row">
          <span>Match</span>
          <span className="match-bar">
            <span className="match-fill" style={{ width: `${Math.round(matchScore * 100)}%` }} />
          </span>
          <span style={{ fontVariantNumeric: 'tabular-nums' }}>
            {Math.round(matchScore * 100)}%
          </span>
        </div>
      )}
      {reason ? <p className="match-reason">“{reason}”</p> : null}

      <div className="dish-foot">
        <span className="price">{rupees(item.price)}</span>
        <button
          className="btn btn-primary btn-sm"
          style={{ marginLeft: 'auto' }}
          onClick={(e) => {
            e.stopPropagation()
            onAdd(item)
          }}
        >
          Add to cart
        </button>
      </div>
    </article>
  )
}

export default function CustomerMenu({ notify }) {
  const { add } = useCart()

  const [menu, setMenu] = useState([])
  const [categories, setCategories] = useState([])
  const [activeCategory, setActiveCategory] = useState('All')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [searchResult, setSearchResult] = useState(null)
  const [sortMode, setSortMode] = useState('featured')
  const [selectedItem, setSelectedItem] = useState(null)

  useEffect(() => {
    async function load() {
      try {
        const [items, cats] = await Promise.all([api.listMenu(), api.categories()])
        setMenu(items)
        setCategories(cats)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const runSearch = useCallback(async (text) => {
    if (!text.trim()) return
    setSearching(true)
    setError('')
    try {
      setSearchResult(await api.search(text.trim(), 12))
    } catch (err) {
      setError(err.message)
      setSearchResult(null)
    } finally {
      setSearching(false)
    }
  }, [])

  function addToCart(item) {
    add(item)
    notify(`${item.name} added to cart`)
  }

  const visible =
    activeCategory === 'All' ? menu : menu.filter((i) => i.category === activeCategory)

  const categoryCounts = categories.reduce(
    (acc, category) => ({
      ...acc,
      [category]: menu.filter((item) => item.category === category).length,
    }),
    {},
  )

  const sortedMenu = [...visible].sort((a, b) => {
    if (sortMode === 'price-low') return a.price - b.price
    if (sortMode === 'price-high') return b.price - a.price
    if (sortMode === 'name') return a.name.localeCompare(b.name)
    return 0
  })

  const constraintPills = searchResult
    ? [
        searchResult.constraints.max_price != null && `≤ ${rupees(searchResult.constraints.max_price)}`,
        searchResult.constraints.min_price != null && `≥ ${rupees(searchResult.constraints.min_price)}`,
        ...searchResult.constraints.require_tags.map((t) => `must be ${t}`),
        ...searchResult.constraints.exclude_tags.map((t) => `no ${t}`),
        ...searchResult.constraints.exclude_terms.slice(0, 3).map((t) => `avoid “${t}”`),
        ...searchResult.constraints.categories.map((c) => `in ${c}`),
      ].filter(Boolean)
    : []

  return (
    <>
      <section className="search-panel">
        <div className="search-title">
          <h2>Ask for what you feel like eating</h2>
        </div>
        <p className="search-sub">
          Plain English works: budgets, dietary needs and vague moods are all understood.
        </p>

        <form
          className="search-bar"
          onSubmit={(e) => {
            e.preventDefault()
            runSearch(query)
          }}
        >
          <input
            className="input"
            placeholder="e.g. something spicy and vegetarian under 200 rupees"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Natural language menu search"
          />
          <button type="submit" className="btn btn-primary" disabled={searching || !query.trim()}>
            {searching ? 'Searching…' : 'Search'}
          </button>
          {searchResult && (
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                setSearchResult(null)
                setQuery('')
              }}
            >
              Clear
            </button>
          )}
        </form>

        <div className="suggestions">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              className="suggestion"
              onClick={() => {
                setQuery(s)
                runSearch(s)
              }}
            >
              {s}
            </button>
          ))}
        </div>

        {!searchResult && (
          <div className="filter-row sort-row">
            <span className="sort-label">Sort</span>
            {[
              ['featured', 'Featured'],
              ['price-low', 'Price: low to high'],
              ['price-high', 'Price: high to low'],
              ['name', 'Name'],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                className="chip-toggle"
                aria-pressed={sortMode === value}
                onClick={() => setSortMode(value)}
              >
                {label}
              </button>
            ))}
          </div>
        )}

        {searchResult && (
          <div className="search-meta">
            <span className={`mode-badge ${searchResult.degraded ? 'degraded' : 'live'}`}>
              {searchResult.search_mode}
            </span>
            <span>{searchResult.took_ms} ms</span>
            {constraintPills.map((pill) => (
              <span className="constraint-pill" key={pill}>
                {pill}
              </span>
            ))}
          </div>
        )}
      </section>

      <Alert>{error}</Alert>

      {loading ? (
        <div className="empty">
          <Spinner /> Loading the menu…
        </div>
      ) : searchResult ? (
        <>
          <div className="section-head">
            <div>
              <h2>Results for “{searchResult.query}”</h2>
              <p>{searchResult.results.length} dish(es) matched, ranked by relevance.</p>
            </div>
          </div>
          {searchResult.results.length === 0 ? (
            <Empty>
              Nothing on the menu satisfies those constraints right now. Try relaxing the
              budget or the dietary filter.
            </Empty>
          ) : (
            <div className="menu-grid">
              {searchResult.results.map((r) => (
                <Dish
                  key={r.item.id}
                  item={r.item}
                  onAdd={addToCart}
                  matchScore={r.score}
                  reason={r.reason}
                />
              ))}
            </div>
          )}
        </>
      ) : (
        <>
          <div className="filter-row">
            {['All', ...categories].map((category) => (
              <button
                type="button"
                key={category}
                className="chip-toggle"
                aria-pressed={activeCategory === category}
                onClick={() => setActiveCategory(category)}
              >
                {category}
                {category !== 'All' && <span className="chip-count">{categoryCounts[category] ?? 0}</span>}
              </button>
            ))}
          </div>

          <div className="section-head compact">
            <p>
              {sortedMenu.length} item{sortedMenu.length === 1 ? '' : 's'} in this view
            </p>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setActiveCategory('All'); setSortMode('featured') }}>
              Reset view
            </button>
          </div>

          {sortedMenu.length === 0 ? (
            <Empty>No dishes in this category yet.</Empty>
          ) : (
            <div className="menu-grid">
              {sortedMenu.map((item) => (
                <div
                  key={item.id}
                  className="dish-wrap"
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedItem(item)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      setSelectedItem(item)
                    }
                  }}
                >
                  <Dish item={item} onAdd={addToCart} />
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {selectedItem && (
        <div className="modal-backdrop" onClick={() => setSelectedItem(null)}>
          <aside className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div className="row" style={{ gap: '0.75rem' }}>
                <span aria-hidden="true" className="dish-emoji">
                  {selectedItem.image_emoji}
                </span>
                <div>
                  <h3>{selectedItem.name}</h3>
                  <p className="muted small">{selectedItem.category}</p>
                </div>
              </div>
              <button type="button" className="btn btn-sm btn-ghost" onClick={() => setSelectedItem(null)}>
                Close
              </button>
            </div>

            <p className="modal-desc">{selectedItem.description}</p>
            <div className="modal-tags">
              <TagList tags={selectedItem.tags} />
            </div>

            <div className="modal-foot">
              <span className="price">{rupees(selectedItem.price)}</span>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => {
                  addToCart(selectedItem)
                  setSelectedItem(null)
                }}
              >
                Add to cart
              </button>
            </div>
          </aside>
        </div>
      )}
    </>
  )
}
