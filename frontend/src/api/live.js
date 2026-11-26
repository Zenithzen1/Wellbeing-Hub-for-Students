// The real backend: FastAPI under /api (Vite proxies it to :8000 in development; in production
// FastAPI serves this app itself, so the origin is the same and the session cookie just works).
//
// Auth is not written on the backend yet (routers/auth.py and deps.get_current_user are TODOs).
// These four calls follow the routes named in routers/auth.py's docstring; adjust the bodies here
// once the backend settles them:
//   POST /api/auth/login     {email, password}            -> sets the session cookie, returns the account
//   POST /api/auth/register  {email, password}            -> creates a student account
//   POST /api/auth/logout                                  -> clears the cookie
//   GET  /api/me                                           -> {account_id, role, pseudonym?, display_name?}

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === 'string' ? detail : `Request failed (${status})`);
    this.status = status;
    this.detail = detail;
  }
}

async function request(method, path, body, query) {
  const url = new URL(`/api${path}`, window.location.origin);
  if (query) for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v);
  const res = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers: body !== undefined ? { 'Content-Type': 'application/json', Accept: 'application/json' } : { Accept: 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    let detail = data && typeof data === 'object' ? data.detail : data;
    if (Array.isArray(detail)) detail = detail.map((d) => d.msg).join('; '); // pydantic validation errors
    throw new ApiError(res.status, detail || res.statusText);
  }
  return data;
}

const get = (p, q) => request('GET', p, undefined, q);
const post = (p, b, q) => request('POST', p, b ?? {}, q);
const patch = (p, b) => request('PATCH', p, b);
const del = (p) => request('DELETE', p);

export const live = {
  mode: 'live',
  // auth (see the note above)
  login: (email, password) => post('/auth/login', { email, password }),
  register: (email, password) => post('/auth/register', { email, password }),
  logout: () => post('/auth/logout'),
  me: () => get('/me'),
  health: () => get('/health'),

  // booking (routers/bookings.py)
  counsellors: () => get('/counsellors'),
  freeDays: (counsellorId, { date, days = 7, firstVisit = false } = {}) =>
    get(`/counsellors/${counsellorId}/free`, { date, days, first_visit: firstVisit }),
  book: (body) => post('/bookings', body),
  myBookings: () => get('/bookings/me'),
  cancelBooking: (id) => del(`/bookings/${id}`),
  availability: (from, to) => get('/counsellor/availability', { from, to }),
  addAvailability: (body) => post('/counsellor/availability', body),
  removeAvailability: (id) => del(`/counsellor/availability/${id}`),
  sessionsOn: (date) => get('/counsellor/sessions', { date }),
  markBooking: (id, status) => patch(`/bookings/${id}`, { status }),

  // waitlist (routers/waitlist.py)
  joinWaitlist: (body) => post('/waitlist', body),
  myWaitlists: () => get('/waitlist'),
  leaveWaitlist: (id) => del(`/waitlist/${id}`),
  acceptOffer: (id, body) => post(`/offers/${id}/accept`, body),
  declineOffer: (id) => post(`/offers/${id}/decline`),
  waitlistCounts: () => get('/counsellor/waitlist'),

  // events (routers/events.py)
  events: (q) => get('/events', q),
  upcomingEvents: (k = 5) => get('/events/upcoming', { k }),
  createEvent: (body) => post('/events', body),
  updateEvent: (id, body) => patch(`/events/${id}`, body),
  deleteEvent: (id) => del(`/events/${id}`),
  register: (id) => post(`/events/${id}/register`),
  unregister: (id) => del(`/events/${id}/register`),

  // notifications (routers/notify.py)
  notifications: (limit = 50) => get('/notifications', { limit }),
  markRead: (id) => post(`/notifications/${id}/read`),
  announce: (body) => post('/admin/announcements', body),
  deadLetters: () => get('/admin/dead-letters'),

  /** Server-Sent Events: reminder, notification, offer, slot_taken, slot_freed. Returns a closer. */
  stream(onEvent) {
    if (typeof EventSource === 'undefined') return () => {};
    const es = new EventSource('/api/stream', { withCredentials: true });
    const kinds = ['reminder', 'notification', 'offer', 'slot_taken', 'slot_freed'];
    const handlers = kinds.map((k) => {
      const h = (e) => { let data = null; try { data = JSON.parse(e.data); } catch { data = e.data; } onEvent(k, data); };
      es.addEventListener(k, h);
      return [k, h];
    });
    return () => { handlers.forEach(([k, h]) => es.removeEventListener(k, h)); es.close(); };
  },
};
