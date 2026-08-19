/**
 * Builds the 4-slide demo deck for the live Teams walkthrough.
 *   node docs/build_deck.js
 */
const pptx = require('pptxgenjs')
const deck = new pptx()

deck.layout = 'LAYOUT_WIDE' // 13.3 x 7.5 in
deck.author = 'Biplab Kar'
deck.title = 'Savora — Food Ordering System with AI-Powered Menu Search'

// Warm terracotta palette — a restaurant product, not a generic SaaS deck.
const INK = '2A211E'
const INK_SOFT = '6B5B54'
const TERRA = 'B85042'
const SAND = 'EFE9DC'
const SAGE = '6E8B7B'
const CREAM = 'FBF8F3'
const WHITE = 'FFFFFF'

const H = 'Bookman Old Style'
const B = 'Calibri'

/* ------------------------------------------------------------------ */
/* Slide 1 — objective                                                 */
/* ------------------------------------------------------------------ */
const s1 = deck.addSlide()
s1.background = { color: INK }

s1.addShape(deck.ShapeType.ellipse, {
  x: 10.4, y: -1.5, w: 5.2, h: 5.2, fill: { color: TERRA, transparency: 82 },
})
s1.addShape(deck.ShapeType.ellipse, {
  x: 11.6, y: 4.6, w: 3.4, h: 3.4, fill: { color: SAGE, transparency: 86 },
})

s1.addText('SAVORA', {
  x: 0.85, y: 0.85, w: 6, h: 0.4,
  fontFace: B, fontSize: 13, bold: true, color: TERRA, charSpacing: 6,
})
s1.addText('Food Ordering System\nwith AI-Powered Menu Search', {
  x: 0.85, y: 1.3, w: 8.2, h: 1.9,
  fontFace: H, fontSize: 38, bold: true, color: WHITE, lineSpacing: 44,
})
s1.addText(
  '“Something spicy and vegetarian under 200 rupees.”  A customer types what they feel like\neating; the system returns available dishes ranked by how well they actually match.',
  {
    x: 0.85, y: 3.35, w: 8.6, h: 1,
    fontFace: B, fontSize: 15, color: SAND, lineSpacing: 24,
  },
)

const pillars = [
  ['Two roles', 'Customer ordering + admin\nkitchen and menu control'],
  ['Hybrid AI search', 'Rules + embeddings + LLM rerank,\nwith an offline fallback'],
  ['Enforced workflow', 'Placed → Confirmed → Preparing\n→ Ready → Picked Up'],
  ['56 backend tests', 'RBAC, state machine, pricing,\nAI degradation ladder'],
]
pillars.forEach(([title, body], i) => {
  const x = 0.85 + i * 2.95
  s1.addShape(deck.ShapeType.roundRect, {
    x, y: 4.75, w: 2.65, h: 1.4, rectRadius: 0.1,
    fill: { color: WHITE, transparency: 92 },
  })
  s1.addText(title, {
    x: x + 0.22, y: 4.95, w: 2.25, h: 0.32, margin: 0,
    fontFace: B, fontSize: 13.5, bold: true, color: TERRA,
  })
  s1.addText(body, {
    x: x + 0.22, y: 5.32, w: 2.25, h: 1, margin: 0,
    fontFace: B, fontSize: 10.5, color: SAND, lineSpacing: 14, valign: 'top',
  })
})

s1.addText('Biplab Kar  ·  AI Software Engineer assignment  ·  KPi-Tech Services', {
  x: 0.85, y: 6.75, w: 9, h: 0.3,
  fontFace: B, fontSize: 11, color: INK_SOFT,
})
s1.addNotes(
  'One line: this is a restaurant ordering app where the search box takes plain English. ' +
  'Two roles, a real order workflow, and an AI layer that is engineered to degrade rather than fail. ' +
  'I will show the architecture, then the AI pipeline, then run the whole flow live.',
)

/* ------------------------------------------------------------------ */
/* Slide 2 — architecture                                              */
/* ------------------------------------------------------------------ */
const s2 = deck.addSlide()
s2.background = { color: CREAM }

s2.addText('System architecture', {
  x: 0.6, y: 0.45, w: 8, h: 0.6, fontFace: H, fontSize: 34, bold: true, color: INK,
})
s2.addText('Routers do HTTP · services do the thinking · models do storage', {
  x: 0.6, y: 1.05, w: 9, h: 0.3, fontFace: B, fontSize: 13, color: INK_SOFT,
})

function band(y, h, label, sub, color) {
  s2.addShape(deck.ShapeType.roundRect, {
    x: 0.6, y, w: 8.5, h, rectRadius: 0.08,
    fill: { color: WHITE }, line: { color: SAND, width: 1 },
  })
  s2.addShape(deck.ShapeType.ellipse, { x: 0.85, y: y + 0.2, w: 0.22, h: 0.22, fill: { color } })
  s2.addText(label, {
    x: 1.2, y: y + 0.13, w: 3, h: 0.35, margin: 0,
    fontFace: B, fontSize: 14, bold: true, color: INK,
  })
  s2.addText(sub, {
    x: 1.2, y: y + 0.5, w: 7.6, h: h - 0.6, margin: 0,
    fontFace: B, fontSize: 11.5, color: INK_SOFT, lineSpacing: 16, valign: 'top',
  })
}

band(1.55, 1.25, 'React 18 + Vite',
  'Customer: menu by category · AI search · cart · order tracking\n' +
  'Admin: dashboard · orders board · menu CRUD     — guarded by role-aware routes', TERRA)

s2.addText('▼   fetch + Bearer JWT   (Vite proxies /api in dev — no CORS in the demo path)', {
  x: 1.2, y: 2.85, w: 7.8, h: 0.3, fontFace: B, fontSize: 10.5, color: SAGE, bold: true,
})

band(3.2, 1.5, 'FastAPI',
  '/auth   /menu   /search   /orders   /dashboard\n' +
  'deps.py → get_current_user → require_admin | require_customer\n' +
  'services: constraints · lexical · gemini · ai_search · order_state', SAGE)

s2.addText('▼   SQLAlchemy 2.0', {
  x: 1.2, y: 4.75, w: 7.8, h: 0.3, fontFace: B, fontSize: 10.5, color: SAGE, bold: true,
})

band(5.1, 1.15, 'SQLite  ·  savora.db',
  'users · menu_items (+ cached embedding) · orders · order_items · order_events', INK)

// side rail — the outside world
s2.addShape(deck.ShapeType.roundRect, {
  x: 9.5, y: 1.55, w: 3.2, h: 2.35, rectRadius: 0.1,
  fill: { color: INK },
})
s2.addText('Google Gemini', {
  x: 9.75, y: 1.8, w: 2.7, h: 0.3, margin: 0,
  fontFace: B, fontSize: 14, bold: true, color: WHITE,
})
s2.addText(
  'text-embedding-004\ngemini-2.0-flash\n\nCalled over plain REST.\nEvery call returns None\non failure — never raises\ninto a request.',
  {
    x: 9.75, y: 2.15, w: 2.7, h: 1.6, margin: 0,
    fontFace: B, fontSize: 10.5, color: SAND, lineSpacing: 14,
  },
)

s2.addShape(deck.ShapeType.roundRect, {
  x: 9.5, y: 4.15, w: 3.2, h: 2.1, rectRadius: 0.1,
  fill: { color: WHITE }, line: { color: SAND, width: 1 },
})
s2.addText('Why SQLite', {
  x: 9.75, y: 4.35, w: 2.7, h: 0.3, margin: 0,
  fontFace: B, fontSize: 13, bold: true, color: TERRA,
})
s2.addText(
  'The evaluation is a live demo on my laptop. A docker-compose that has to be healthy five minutes before the call is risk without benefit at this data volume. DATABASE_URL is the only change to move to Postgres.',
  {
    x: 9.75, y: 4.68, w: 2.7, h: 1.45, margin: 0,
    fontFace: B, fontSize: 9.5, color: INK_SOFT, lineSpacing: 12.5, valign: 'top',
  },
)

s2.addText('8 backend dependencies  ·  3 frontend dependencies', {
  x: 0.6, y: 6.55, w: 9, h: 0.3, fontFace: B, fontSize: 11, italic: true, color: INK_SOFT,
})
s2.addNotes(
  'Three layers and one external service. The layering rule matters more than the boxes: ' +
  'no business logic lives in a router. Order transitions live in order_state.py, ranking in ai_search.py, ' +
  'which is why the API, the tests and the UI button states all read from one definition. ' +
  'SQLite is a demo-risk decision, not a scaling opinion — I can defend both halves of that.',
)

/* ------------------------------------------------------------------ */
/* Slide 3 — the AI pipeline                                           */
/* ------------------------------------------------------------------ */
const s3 = deck.addSlide()
s3.background = { color: CREAM }

s3.addText('The AI search pipeline', {
  x: 0.6, y: 0.45, w: 9, h: 0.6, fontFace: H, fontSize: 34, bold: true, color: INK,
})
s3.addText('Four stages. Each one degrades on its own instead of taking the search down.', {
  x: 0.6, y: 1.05, w: 10, h: 0.3, fontFace: B, fontSize: 13, color: INK_SOFT,
})

s3.addShape(deck.ShapeType.roundRect, {
  x: 0.6, y: 1.5, w: 12.1, h: 0.55, rectRadius: 0.08,
  fill: { color: SAND },
})
s3.addText('“something spicy and vegetarian under 200 rupees”', {
  x: 0.85, y: 1.58, w: 11.6, h: 0.4, margin: 0,
  fontFace: B, fontSize: 15, bold: true, italic: true, color: INK,
})

const stages = [
  ['1  Constraints', 'Regex rules first, Gemini second.\nOn conflict the rules win.',
    'max_price = 200\nrequire = spicy, vegetarian', 'no LLM → rules only'],
  ['2  Candidate set', 'Hard filters in SQL: price, diet,\nallergens, availability.',
    'The model never gets to\noverride a stated budget.', 'always runs'],
  ['3  Recall', 'Cosine over embeddings cached\non each row, fingerprinted.',
    'One embedding call per\nsearch — the query.', 'no vectors → BM25'],
  ['4  Rerank', 'Gemini scores the top 12 and\nwrites a one-line reason.',
    'Blend 0.7 × LLM +\n0.3 × retrieval.', 'no rerank → recall order'],
]

stages.forEach(([title, body, detail, fallback], i) => {
  const x = 0.6 + i * 3.09
  s3.addShape(deck.ShapeType.roundRect, {
    x, y: 2.35, w: 2.85, h: 2.75, rectRadius: 0.1,
    fill: { color: WHITE }, line: { color: SAND, width: 1 },
  })
  s3.addText(title, {
    x: x + 0.22, y: 2.55, w: 2.4, h: 0.3, margin: 0,
    fontFace: B, fontSize: 14, bold: true, color: TERRA,
  })
  s3.addText(body, {
    x: x + 0.22, y: 2.92, w: 2.45, h: 0.8, margin: 0,
    fontFace: B, fontSize: 11, color: INK, lineSpacing: 15, valign: 'top',
  })
  s3.addShape(deck.ShapeType.roundRect, {
    x: x + 0.22, y: 3.72, w: 2.45, h: 0.72, rectRadius: 0.06,
    fill: { color: SAND },
  })
  s3.addText(detail, {
    x: x + 0.34, y: 3.8, w: 2.25, h: 0.6, margin: 0,
    fontFace: B, fontSize: 10, color: INK_SOFT, lineSpacing: 13, valign: 'top',
  })
  s3.addText(`↓  ${fallback}`, {
    x: x + 0.22, y: 4.58, w: 2.45, h: 0.35, margin: 0,
    fontFace: B, fontSize: 10, bold: true, color: SAGE,
  })
  if (i < 3) {
    s3.addText('→', {
      x: x + 2.87, y: 3.4, w: 0.24, h: 0.4, margin: 0, align: 'center',
      fontFace: B, fontSize: 18, bold: true, color: TERRA,
    })
  }
})

const claims = [
  ['Hard constraints never reach the model', 'Price, diet and allergens are SQL predicates. A test proves an LLM trying to widen ₹200 → ₹5000 is ignored.'],
  ['Soft preferences only steer ranking', '“Light”, “not fried” on a 40-item menu would empty the results if hard-filtered. They rank; they do not exclude.'],
  ['The response says which path ran', 'search_mode, degraded and notes are part of the contract and shown in the UI. A silent downgrade is the worse bug.'],
]
claims.forEach(([title, body], i) => {
  const x = 0.6 + i * 4.12
  s3.addShape(deck.ShapeType.ellipse, { x, y: 5.5, w: 0.2, h: 0.2, fill: { color: TERRA } })
  s3.addText(title, {
    x: x + 0.32, y: 5.42, w: 3.6, h: 0.35, margin: 0,
    fontFace: B, fontSize: 12, bold: true, color: INK,
  })
  s3.addText(body, {
    x: x + 0.32, y: 5.78, w: 3.6, h: 0.9, margin: 0,
    fontFace: B, fontSize: 10.5, color: INK_SOFT, lineSpacing: 14, valign: 'top',
  })
})
s3.addNotes(
  'This is the slide I expect questions on. The key idea: an LLM is good at judging semantic fit and bad at arithmetic, ' +
  'so I never delegate a number to it. Under 200 means under 200, enforced in SQL. ' +
  'The fallback ladder is real — I can pull the API key mid-demo and search keeps working, ' +
  'and the badge in the UI changes from semantic+rerank to lexical so nobody is fooled.',
)

/* ------------------------------------------------------------------ */
/* Slide 4 — end-to-end workflow                                       */
/* ------------------------------------------------------------------ */
const s4 = deck.addSlide()
s4.background = { color: CREAM }

s4.addText('End-to-end workflow', {
  x: 0.6, y: 0.45, w: 9, h: 0.6, fontFace: H, fontSize: 34, bold: true, color: INK,
})
s4.addText('Search → cart → order → kitchen → dashboard, with the state machine enforced server-side', {
  x: 0.6, y: 1.05, w: 11, h: 0.3, fontFace: B, fontSize: 13, color: INK_SOFT,
})

const flow = ['Placed', 'Confirmed', 'Preparing', 'Ready', 'Picked Up']
const stageFill = ['D3B8A8', 'C79684', 'B85042', '96382F', '6E2620']
flow.forEach((label, i) => {
  const x = 0.6 + i * 2.42
  s4.addShape(deck.ShapeType.roundRect, {
    x, y: 1.65, w: 2.2, h: 0.72, rectRadius: 0.1,
    fill: { color: stageFill[i] },
  })
  s4.addText(label, {
    x, y: 1.82, w: 2.2, h: 0.38, align: 'center', margin: 0,
    fontFace: B, fontSize: 14, bold: true, color: i < 2 ? INK : WHITE,
  })
  if (i < 4) {
    s4.addText('→', {
      x: x + 2.2, y: 1.8, w: 0.22, h: 0.4, align: 'center', margin: 0,
      fontFace: B, fontSize: 16, bold: true, color: INK_SOFT,
    })
  }
})

s4.addText(
  'Forward-only · cancellable up to Preparing · terminal states accept nothing · illegal transition = 422 naming what IS allowed · every move appended to order_events',
  { x: 0.6, y: 2.5, w: 12.1, h: 0.3, fontFace: B, fontSize: 11, color: INK_SOFT },
)

const columns = [
  ['Customer', TERRA, [
    'Searches in plain English, sees a match % and the reason',
    'Cart sends ids and quantities only — never prices',
    'Order card polls every 8s and shows a live progress rail',
  ]],
  ['Admin', SAGE, [
    'Orders board renders buttons from the server’s allowed_transitions',
    'Menu CRUD; deleting a dish that appears on past orders is a 409',
    'Dashboard: revenue, AOV, orders by status, popular items, by hour',
  ]],
  ['Guarantees', INK, [
    'Prices re-read server-side; order lines snapshot name and price',
    'A customer fetching another customer’s order gets 404, not 403',
    'Unavailable dishes never enter search results or a new order',
  ]],
]
columns.forEach(([title, color, items], i) => {
  const x = 0.6 + i * 4.12
  s4.addShape(deck.ShapeType.roundRect, {
    x, y: 3, w: 3.85, h: 2.28, rectRadius: 0.1,
    fill: { color: WHITE }, line: { color: SAND, width: 1 },
  })
  s4.addShape(deck.ShapeType.ellipse, { x: x + 0.25, y: 3.25, w: 0.22, h: 0.22, fill: { color } })
  s4.addText(title, {
    x: x + 0.58, y: 3.18, w: 3, h: 0.32, margin: 0,
    fontFace: B, fontSize: 15, bold: true, color: INK,
  })
  s4.addText(
    items.map((t, idx) => ({
      text: t,
      options: { bullet: { indent: 14 }, breakLine: idx !== items.length - 1 },
    })),
    {
      x: x + 0.28, y: 3.62, w: 3.35, h: 1.8, margin: 0,
      fontFace: B, fontSize: 10.5, color: INK_SOFT, lineSpacing: 14, paraSpaceAfter: 6, valign: 'top',
    },
  )
})

s4.addShape(deck.ShapeType.roundRect, {
  x: 0.6, y: 5.75, w: 12.1, h: 1.1, rectRadius: 0.1, fill: { color: INK },
})
s4.addText('If I had another week', {
  x: 0.9, y: 5.9, w: 3, h: 0.3, margin: 0,
  fontFace: B, fontSize: 12.5, bold: true, color: TERRA,
})
s4.addText(
  'Alembic migrations  ·  refresh tokens with a shorter TTL  ·  rate-limit + cache the public search endpoint  ·  move recall into the DB (sqlite-vec / pgvector)  ·  idempotency key on POST /orders  ·  a labelled query set so search quality is a number, not a vibe',
  {
    x: 0.9, y: 6.22, w: 11.5, h: 0.55, margin: 0,
    fontFace: B, fontSize: 10.5, color: SAND, lineSpacing: 14,
  },
)
s4.addNotes(
  'Close on the live run: sign in as a customer, search, order; switch to admin, push it through every stage, ' +
  'show the dashboard move. Then the honest part — what is not built. Migrations first, then token refresh, ' +
  'then rate-limiting the search endpoint because it is public and costs money per call.',
)

deck.writeFile({ fileName: '/home/claude/savora/docs/Savora-demo-deck.pptx' }).then(() => {
  console.log('written')
})
