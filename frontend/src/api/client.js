/**
 * Single place where the frontend talks to the API.
 *
 * Two things it centralises: the bearer token, and error shape. Every
 * failure becomes an Error whose message is the backend's `detail` string,
 * so components can render `err.message` without knowing the status code.
 */
const TOKEN_KEY = 'savora.token'

export function getToken() {
  return window.__savoraToken ?? sessionStorage.getItem(TOKEN_KEY) ?? null
}

export function setToken(token) {
  window.__savoraToken = token
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token)
    else sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    /* private mode — fall back to the in-memory copy above */
  }
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function request(path, { method = 'GET', body, auth = true } = {}) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const token = getToken()
  if (auth && token) headers.Authorization = `Bearer ${token}`

  let response
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError('Cannot reach the server. Is the backend running on port 8000?', 0)
  }

  if (response.status === 204) return null

  let payload = null
  const text = await response.text()
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = { detail: text }
    }
  }

  if (!response.ok) {
    const detail =
      typeof payload?.detail === 'string'
        ? payload.detail
        : `Request failed (${response.status})`
    if (response.status === 401 && getToken()) setToken(null)
    throw new ApiError(detail, response.status)
  }
  return payload
}

export const api = {
  // auth
  login: (email, password) =>
    request('/auth/login', { method: 'POST', body: { email, password }, auth: false }),
  register: (email, full_name, password) =>
    request('/auth/register', {
      method: 'POST',
      body: { email, full_name, password },
      auth: false,
    }),
  me: () => request('/auth/me'),

  // menu
  listMenu: (params = {}) => {
    const query = new URLSearchParams()
    if (params.category) query.set('category', params.category)
    if (params.availableOnly === false) query.set('available_only', 'false')
    const suffix = query.toString()
    return request(`/menu${suffix ? `?${suffix}` : ''}`, { auth: true })
  },
  categories: () => request('/menu/categories', { auth: false }),
  createItem: (item) => request('/menu', { method: 'POST', body: item }),
  updateItem: (id, patch) => request(`/menu/${id}`, { method: 'PATCH', body: patch }),
  toggleAvailability: (id) => request(`/menu/${id}/availability`, { method: 'PATCH' }),
  deleteItem: (id) => request(`/menu/${id}`, { method: 'DELETE' }),

  // ai search
  search: (q, limit = 8) =>
    request(`/search?q=${encodeURIComponent(q)}&limit=${limit}`, { auth: false }),
  aiHealth: () => request('/search/health', { auth: false }),

  // orders
  placeOrder: (items, notes = '') =>
    request('/orders', { method: 'POST', body: { items, notes } }),
  listOrders: (params = {}) => {
    const query = new URLSearchParams()
    if (params.status) query.set('status', params.status)
    if (params.activeOnly) query.set('active_only', 'true')
    const suffix = query.toString()
    return request(`/orders${suffix ? `?${suffix}` : ''}`)
  },
  getOrder: (id) => request(`/orders/${id}`),
  updateOrderStatus: (id, status) =>
    request(`/orders/${id}/status`, { method: 'PATCH', body: { status } }),

  // dashboard
  dashboard: () => request('/dashboard'),
}
