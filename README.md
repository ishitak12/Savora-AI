# Savora — Food Ordering System with AI-Powered Menu Search

A restaurant ordering application with two roles. **Customers** browse the menu,
search it in plain English, build a cart and track their order. **Admins** manage
the menu, move orders through the kitchen workflow, and watch a live dashboard.

The AI component answers queries like *"something spicy and vegetarian under 200
rupees"* or *"a light lunch that is not fried"* by combining deterministic
constraint filtering, embedding-based semantic recall, and an LLM reranker — and
it keeps working when the LLM is unavailable.

Built for the KPi-Tech AI Software Engineer assignment.

---

## Table of contents

- [Tech stack](#tech-stack)
- [Quick start](#quick-start)
- [Architecture](#architecture)
- [The AI search pipeline](#the-ai-search-pipeline)
- [Order workflow](#order-workflow)
- [API reference](#api-reference)
- [Data model](#data-model)
- [Design decisions](#design-decisions)
- [Testing](#testing)
- [Assumptions](#assumptions)
- [Known gaps and what I'd do next](#known-gaps-and-what-id-do-next)

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | **FastAPI** (Python 3.11) | Pydantic validation and generated OpenAPI docs come free; async-ready without forcing async |
| ORM | **SQLAlchemy 2.0** (typed `Mapped[]` style) | Explicit schema, no magic strings |
| Database | **SQLite** | One file, no daemon. A demo that must boot on an unknown machine should not depend on a running Postgres |
| Auth | **JWT** (HS256) + PBKDF2-SHA256 password hashing | Stateless tokens; stdlib KDF avoids the passlib/bcrypt native-wheel breakage that bites on demo day |
| AI | **Groq** for JSON extraction + reranking, with optional Gemini embeddings; called over plain REST with `httpx` | One less SDK to install; the search path still degrades cleanly if the model is unavailable |
| Frontend | **React 18 + Vite**, React Router | Fast dev server, tiny build, no framework ceremony |
| Styling | Hand-written CSS with design tokens | No Tailwind build step; light/dark themes swap in one place |
| Charts | Hand-rolled SVG | No chart library to install; full control over marks and a table view for every chart |
| Tests | **pytest** (56 tests) | Covers auth, RBAC, the order state machine, dashboard maths, and the AI fallback ladder |

Backend runtime dependencies: 8 packages. Frontend runtime dependencies: 3.

---

## Quick start

**Prerequisites:** Python 3.11+, Node 18+.

### 1. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env          # optional — add your Groq key here
python -m app.db.seed --reset # 40 dishes, 3 users, 14 sample orders
uvicorn app.main:app --reload --port 8000
```

API on <http://localhost:8000>, interactive docs on <http://localhost:8000/docs>.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

App on <http://localhost:5173>. Vite proxies `/api` to port 8000, so the browser
only ever talks to one origin and CORS never enters the picture in development.
<!--
### 3. Sign in

| Role | Email | Password |
|---|---|---|
| Admin | `admin@savora.in` | `admin123` |
| Customer | `customer@savora.in` | `customer123` |   

The login screen has buttons that fill these in. -->

### Enabling the AI path

Without a key the app runs in **offline mode** — search still works, using BM25
lexical retrieval with culinary synonym expansion. To turn on the live LLM path,
put a Groq API key in `backend/.env`:

```dotenv
AI_PROVIDER=groq
GROQ_API_KEY=your-key-here
```

then re-run `python -m app.db.seed`. Groq handles constraint extraction and
reranking; the menu recall path stays lexical unless Gemini embeddings are
configured as well. The UI badge next to each search result and on the admin
dashboard shows which mode actually served the request.

If you want semantic recall too, keep `GEMINI_API_KEY` and leave
`GEMINI_EMBED_MODEL=gemini-embedding-001`.

If you see a 404 from the embedding call, set `GEMINI_EMBED_MODEL=gemini-embedding-001`.

---

## Architecture

```
┌───────────────────────────── BROWSER ──────────────────────────────┐
│  React 18 + Vite                                                   │
│                                                                    │
│   AuthContext (JWT)        CartContext (client-side only)          │
│         │                        │                                 │
│   ┌─────┴──────┐          ┌──────┴───────┐                         │
│   │ CUSTOMER   │          │    ADMIN     │                         │
│   │ Menu       │          │ Dashboard    │                         │
│   │ AI search  │          │ Orders board │                         │
│   │ Cart       │          │ Menu CRUD    │                         │
│   │ My orders  │          │              │                         │
│   └─────┬──────┘          └──────┬───────┘                         │
└─────────┼─────────────────────────┼────────────────────────────────┘
          │        fetch + Bearer JWT (Vite proxy in dev)
┌─────────▼─────────────────────────▼────────────────────────────────┐
│  FastAPI                                                           │
│                                                                    │
│   /api/auth      register · login · me                             │
│   /api/menu      list · get · create · update · toggle · delete    │
│   /api/search    natural-language search · ai health               │
│   /api/orders    place · list (role-scoped) · get · status         │
│   /api/dashboard aggregates (admin only)                           │
│         │                                                          │
│   deps.py: get_current_user → require_admin / require_customer     │
│         │                                                          │
│   services/                                                        │
│     constraints.py  regex constraint extraction (hard filters)     │
│     lexical.py      BM25 + synonym expansion (offline fallback)    │
│     gemini.py       embeddings + JSON chat, returns None on failure│
│     ai_search.py    the pipeline orchestrator                      │
│     order_state.py  the status state machine                       │
│         │                                                          │
│   SQLAlchemy ──► SQLite (savora.db)                                │
│     users · menu_items · orders · order_items · order_events       │
└────────────────────────────┬───────────────────────────────────────┘
                             │ (only when a key is configured)
                    ┌────────▼────────┐
                    │  Google Gemini  │
                    │  embeddings +   │
                    │  flash reranker │
                    └─────────────────┘
```

Layering rule: **routers do HTTP, services do thinking, models do storage.** A
router never contains business logic — order transitions live in
`order_state.py`, ranking lives in `ai_search.py` — which is why the same rules
are enforced identically for the API, the tests, and the UI's button states.

---

## The AI search pipeline

```
  "something spicy and vegetarian under 200 rupees"
                    │
  ┌─────────────────▼─────────────────┐
  │ 1. CONSTRAINT EXTRACTION          │
  │    regex rules  ──┐               │   max_price = 200
  │                   ├──► merge      │   require   = [spicy, vegetarian]
  │    Gemini JSON  ──┘  (rules win)  │
  └─────────────────┬─────────────────┘
  ┌─────────────────▼─────────────────┐
  │ 2. CANDIDATE SET (SQL)            │   available_only = TRUE
  │    hard filters, never the model  │   price/diet/allergen predicates
  └─────────────────┬─────────────────┘
  ┌─────────────────▼─────────────────┐
  │ 3. RECALL                         │
  │    cosine over cached embeddings  │───fail──► BM25 + synonyms
  └─────────────────┬─────────────────┘
  ┌─────────────────▼─────────────────┐
  │ 4. RERANK                         │
  │    Gemini scores top-12 + reason  │───fail──► keep retrieval order
  │    blend 0.7 × LLM + 0.3 × recall │
  └─────────────────┬─────────────────┘
                    ▼
   ranked dishes + match % + one-line reason + search_mode
```

**Why this shape, and not "just ask the LLM":**

1. **Hard constraints are not negotiable.** "Under 200" returning a ₹240 dish is a
   correctness bug, not a ranking imperfection. Price, diet and allergens are SQL
   predicates. The model cannot override them — there is a test that proves an LLM
   trying to widen the budget from 200 to 5000 gets ignored.
2. **Allergens are stricter than preferences.** "Without nuts" becomes a hard tag
   exclusion, not a text match, so a dish tagged `contains-nuts` is filtered out
   even if the word "nut" never appears in its description.
3. **Availability is a filter, not a signal.** The brief says results come "from
   what is currently available", so unavailable items never enter the candidate set.
4. **Embeddings are cached on the row** with a SHA-256 fingerprint of the item's
   searchable text. Editing a description automatically invalidates its vector. A
   search therefore costs exactly one embedding call — the query — not N+1.
5. **Every stage degrades independently.** Losing the reranker does not lose
   semantic recall. Losing embeddings does not lose search. Losing the network
   entirely still returns ranked results.
6. **The response says which path ran.** `search_mode`, `degraded` and `notes` are
   part of the API contract and are rendered in the UI. A silent downgrade is a
   worse bug than a loud one.

Soft preferences ("light", "not fried", "comforting") are deliberately *not* hard
filters — with a 40-item menu, hard-filtering on a vague adjective empties the
result set. They steer ranking, and the text exclusion only applies if something
survives it.

---

## Order workflow

```
  Placed ──► Confirmed ──► Preparing ──► Ready ──► Picked Up
    │            │             │
    └────────────┴─────────────┴──► Cancelled
```

- **Forward-only.** Reverting `Ready → Preparing` would double-count revenue and
  corrupt throughput figures.
- **Cancellable up to Preparing.** Once a dish is `Ready` it has been cooked;
  cancelling it is a refund decision, not a state transition.
- **Terminal states are terminal.** `Picked Up` and `Cancelled` accept nothing.
- An illegal transition returns **422** with a message naming what *is* allowed.
- Every transition appends to `order_events`, giving a full audit trail
  (who moved it, from what, when) without losing `orders.status` as the fast read.

The API returns `allowed_transitions` on every order, so the admin UI renders its
buttons from the server's rules rather than duplicating the state machine in
JavaScript.

---

## API reference

Base path `/api`. Auth is `Authorization: Bearer <token>`.

### Auth

| Method | Path | Access | Notes |
|---|---|---|---|
| POST | `/auth/register` | public | Always creates a **customer**; self-registering as admin is 403 |
| POST | `/auth/login` | public | 401 with an identical message for bad email *and* bad password |
| GET | `/auth/me` | any user | Verifies a persisted token on app boot |

### Menu

| Method | Path | Access | Notes |
|---|---|---|---|
| GET | `/menu` | public | `?category=`, `?available_only=false` (admin view), `?q=` |
| GET | `/menu/categories` | public | Distinct categories of available items |
| GET | `/menu/{id}` | public | 404 if unknown |
| POST | `/menu` | admin | 201; embeds the new item on write |
| PATCH | `/menu/{id}` | admin | Partial update; re-embeds if the text changed |
| PATCH | `/menu/{id}/availability` | admin | Toggle |
| DELETE | `/menu/{id}` | admin | 204, or **409** if the dish appears on past orders |

### Search

| Method | Path | Access | Notes |
|---|---|---|---|
| GET | `/search?q=&limit=` | public | Browsing shouldn't need an account. Ordering does |
| GET | `/search/health` | public | Whether the AI path is configured and reachable |

### Orders

| Method | Path | Access | Notes |
|---|---|---|---|
| POST | `/orders` | any user | Server re-reads prices and availability; 409 if an item went off-menu |
| GET | `/orders` | any user | Customers see only their own — scoped in the query, not the client |
| GET | `/orders/{id}` | owner or admin | **404** (not 403) for someone else's order, so ids can't be probed |
| PATCH | `/orders/{id}/status` | admin | 422 on an illegal transition, 409 if already in that status |

### Dashboard

| Method | Path | Access | Notes |
|---|---|---|---|
| GET | `/dashboard` | admin | Orders by status, popular items, today's revenue, hourly revenue, AOV |

**Status codes used, and why:** `201` create · `204` delete · `401` unauthenticated
· `403` authenticated but wrong role · `404` unknown *or deliberately hidden* ·
`409` a conflict with current state (duplicate email, item unavailable, item
referenced by history) · `422` well-formed request, invalid content or an illegal
state transition.

---

## Data model

```
users                    menu_items
├── id                   ├── id
├── email (unique)       ├── name, description, category
├── full_name            ├── price
├── hashed_password      ├── tags_raw          "vegetarian,spicy"
└── role  admin|customer ├── is_available
        │                ├── embedding_json    cached vector
        │                └── embedding_fingerprint  SHA-256 of search text
        │                        │
   orders ◄─────────────┐        │
   ├── id               │        │
   ├── order_code       │   order_items
   ├── customer_id ─────┘   ├── order_id ──► orders
   ├── status               ├── menu_item_id ──► menu_items
   ├── total_amount         ├── item_name    ← snapshot
   ├── notes                ├── unit_price   ← snapshot
   └── created_at           └── quantity
        │
   order_events
   ├── order_id ──► orders
   ├── from_status, to_status
   ├── actor_email
   └── created_at
```

Two deliberate choices here:

- **`order_items` snapshots name and price.** An order is a financial record. If
  the admin reprices Paneer Tikka tomorrow, yesterday's receipts must not change.
  There is a test asserting exactly this.
- **`tags_raw` is a packed string, not a join table.** SQLite has no array type,
  the tag vocabulary is five values, and the catalogue is dozens of rows. A join
  table would be ceremony. It is a documented trade-off, not an oversight — at
  thousands of items with tag-faceted browse, it should become a real table.

---

## Design decisions

**SQLite over Postgres.** The evaluation is a live demo on my machine. A
docker-compose that needs a healthy container five minutes before a Teams call is
risk without benefit at this data volume. `DATABASE_URL` is the only thing that
changes to move to Postgres.

**PBKDF2 over bcrypt.** bcrypt needs a compiled wheel and passlib's version
handshake with it is a known import-time failure. 260k-iteration PBKDF2-SHA256
from the standard library removes a native dependency. In production behind a
real deployment pipeline, argon2id is the better primitive.

**JWT over server sessions.** No session store to run; the token carries the role
claim, but the role is re-read from the database on every request — the claim is
never trusted on its own.

**Embeddings computed on write, not on read.** Search latency should not include
embedding 40 dishes. The fingerprint column makes the cache self-invalidating.

**Polling over websockets.** The order board refreshes every 8 seconds and the
dashboard every 15. Websockets would need a connection manager, reconnect logic
and a second failure mode, to save a few seconds of latency in a restaurant where
food takes fifteen minutes.

**Hand-rolled SVG charts.** No charting dependency, and every chart carries a
"Show table" toggle so numbers are never encoded in colour alone. The status
chart's colour ramp is a single-hue *ordinal* ramp (the workflow is an ordered
progression, not unrelated categories), validated for lightness monotonicity,
adjacent-step separation and contrast against both the light and dark surface.

**`create_all` over Alembic.** For a greenfield SQLite demo, migrations are
overhead. Adding Alembic is the first thing I'd do before a second developer or a
second environment exists.

---

## Testing

```bash
cd backend && python -m pytest -q      # 56 tests
```

| File | What it locks down |
|---|---|
| `test_auth_and_menu.py` | Login, token issue, no-enumeration on failed login, admin-escalation block, menu CRUD, validation rejects |
| `test_orders.py` | Server-side pricing, duplicate-line merge, unavailable-item 409, **cross-customer isolation**, the full happy path, every illegal transition, price-snapshot immutability |
| `test_search.py` | Constraint parser as a pure function, hard price/diet guarantees, availability filter, empty-result explanation, sort order |
| `test_ai_pipeline.py` | The Gemini path with a stubbed client: `semantic+rerank` happy path, **hallucinated-id rejection**, reranker-failure degradation, embedding-failure degradation, LLM-cannot-widen-a-constraint, embedding cache invalidation |
| `test_dashboard.py` | RBAC, empty-state zeros, revenue counts only confirmed orders, cancelled orders excluded, popularity ranking |

Tests run with **no API key**, which is the degraded path on purpose: the fallback
is the part that must never break, and it is the part CI can test deterministically
without network access or spend. The live path is covered via a stubbed client, so
the code that runs with a key is exercised too.

There is also `e2e_check.py` at the repo root — a Playwright script that drives a
real browser through sign-in, AI search, checkout, and the full admin workflow,
failing on any console error. It is a verification tool, not part of the suite.

---

## Assumptions

1. **Single restaurant, single kitchen.** No multi-tenancy, no branches.
2. **Pickup, not delivery.** The workflow ends at `Picked Up`; there is no rider,
   address or ETA model.
3. **No payment integration.** An order is "revenue" once it reaches `Confirmed`.
   A real system would gate that on a payment webhook.
4. **"Today" is a calendar day in the server's local timezone**, not UTC — a
   restaurant's day in India does not align with a UTC day.
5. **Admin accounts are provisioned, not self-registered.** The seeder creates
   them; in production this would be an invite flow.
6. **The kitchen is trusted.** Any admin can move any order; there is no
   per-station permission model.
7. **Menu descriptions are the search corpus.** Search quality is downstream of
   description quality — which is why the admin form says so next to the field.
8. **Prices are whole rupees**, no tax or service charge modelling.

---

## Known gaps and what I'd do next

Ordered by what I'd actually do first:

1. **Alembic migrations.** `create_all` cannot evolve a schema that has data in it.
2. **Refresh tokens + shorter access-token TTL.** 12 hours is too long; there is
   no revocation path today.
3. **Rate-limit `/api/search`.** It is public and it costs money per call once a
   key is configured. A per-IP bucket plus a small query cache would cut both
   spend and latency, since customers ask similar things.
4. **Move recall into the database.** Cosine similarity in Python is fine at 40
   items and wrong at 40,000. `sqlite-vec` or pgvector, with the same interface.
5. **Idempotency key on `POST /orders`.** A double-tap on a flaky connection
   currently creates two orders.
6. **Optimistic concurrency on status updates.** Two admins clicking at once: the
   second write silently wins today. An `If-Match` on `updated_at` would make it a
   409 the UI can explain.
7. **Evaluate the search, don't eyeball it.** A labelled set of ~50 query→expected
   pairs and a recall@5 / MRR number, so a prompt change is a measurement instead
   of a vibe.
8. **Frontend tests.** The backend has 56; the UI has a Playwright smoke script and
   nothing else. Vitest + Testing Library on the cart maths and the rail component.
9. **Structured logging with request ids**, so a slow search can be traced through
   constraint extraction, recall and rerank individually.
10. **Accessibility audit.** Keyboard traps in the cart drawer, focus management on
    route change, and a real screen-reader pass.

---

## Repository layout

```
savora/
├── backend/
│   ├── app/
│   │   ├── api/          routers: auth, menu, search, orders, dashboard, deps
│   │   ├── core/         config, security (hashing + JWT)
│   │   ├── db/           session, seed
│   │   ├── models/       SQLAlchemy models
│   │   ├── schemas/      pydantic request/response contracts
│   │   ├── services/     constraints, lexical, gemini, ai_search, order_state
│   │   └── main.py       app factory, CORS, error handlers
│   ├── tests/            56 pytest tests
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── api/          single fetch client
│   │   ├── components/   Charts, CartDrawer, shared UI
│   │   ├── context/      AuthContext, CartContext
│   │   ├── pages/        Login, CustomerMenu, MyOrders, AdminMenu,
│   │   │                 AdminOrders, AdminDashboard
│   │   └── styles/       design tokens + component CSS
│   ├── package.json
│   └── vite.config.js
├── docs/                 architecture diagrams, demo deck
├── e2e_check.py          Playwright end-to-end verification
└── README.md
```
