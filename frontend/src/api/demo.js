// Demo mode: an in-browser stand-in for the FastAPI backend, with the same call names and the same
// response shapes as live.js, so every screen can be used before auth exists on the server.
// It follows the backend's own rules (services/booking.py, waitlist.py, events.py):
//   45-minute sessions, 60 for a first visit, starts on the quarter hour, up to 60 days ahead;
//   a waitlist line can be joined only when the counsellor has no free time in the next 7 days;
//   an offer is held 30 minutes; events register until full, then join a FIFO line.
// State lives in sessionStorage, so a reload keeps what you did and a new tab starts fresh.

import { ApiError } from './live.js';
import { addDays, atLocal, dubaiMidnight, isoDate } from './time.js';

const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;
const SESSION = 45, FIRST_VISIT = 60;
const HOLD = 30 * MIN;
const REASONS = ['academic_stress', 'anxiety', 'low_mood', 'relationships', 'sleep', 'other'];
const ME = '#47C32E';
const KEY = 'wbh-demo-state-v1';

const iso = (ms) => new Date(ms).toISOString().replace('.000Z', 'Z');
const ms = (d) => new Date(d).getTime();
const overlaps = (a0, a1, b0, b1) => a0 < b1 && b0 < a1;
const wait = (v) => new Promise((r) => setTimeout(() => r(structuredClone(v)), 220 + Math.random() * 180));
const fail = (status, detail) => Promise.reject(new ApiError(status, detail));

// a small seeded random, so the demo week looks the same on every load
function rng(seed) { return () => ((seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296); }
const tag = (r) => '#' + Math.floor(r() * 0xffffff).toString(16).toUpperCase().padStart(6, '0');

// 1 = Monday ... 7 = Sunday, for a Dubai date (noon there is 08:00 UTC the same day)
function weekday(dayIso) { const d = new Date(dubaiMidnight(dayIso).getTime() + 12 * HOUR).getUTCDay(); return d === 0 ? 7 : d; }

function seed() {
  const r = rng(47);
  const today = isoDate();
  const now = Date.now();
  let id = 1;
  const s = {
    seq: 100,
    counsellors: [
      { id: 1, display_name: 'Dr Noor', specialties: ['anxiety', 'study'] },
      { id: 2, display_name: 'Dr Mehta', specialties: ['sleep', 'low mood'] },
    ],
    availability: [], bookings: [], waitlist: [], offers: [], events: [], notifications: [], announcements: [],
    deadLetters: [
      { id: 1, kind: 'email', title: 'Session in 24 hours', attempts: 4, last_attempt_at: iso(now - 3 * HOUR), last_error: 'SMTP 451: mailbox temporarily unavailable' },
      { id: 2, kind: 'email', title: 'Yoga in 1 hour', attempts: 4, last_attempt_at: iso(now - 26 * HOUR), last_error: 'Connection timed out' },
    ],
  };
  // open hours: Dr Noor Mon-Fri 9-13 and 14-17; Dr Mehta Mon-Fri 10-16
  for (let d = -14; d <= 28; d++) {
    const day = addDays(today, d);
    const wd = weekday(day);
    if (wd > 5) continue;
    s.availability.push({ id: id++, counsellor_id: 1, start: atLocal(day, '09:00'), end: atLocal(day, '13:00'), kind: 'open', note: '' });
    s.availability.push({ id: id++, counsellor_id: 1, start: atLocal(day, '14:00'), end: atLocal(day, '17:00'), kind: 'open', note: '' });
    s.availability.push({ id: id++, counsellor_id: 2, start: atLocal(day, '10:00'), end: atLocal(day, '16:00'), kind: 'open', note: '' });
    if (wd === 3) s.availability.push({ id: id++, counsellor_id: 1, start: atLocal(day, '12:00'), end: atLocal(day, '13:00'), kind: 'blocked', note: 'Team meeting' });
  }
  // other students' sessions: Dr Noor about half full, Dr Mehta full for the next 7 days
  const book = (cid, startIso, mins, extra = {}) => s.bookings.push({
    id: id++, counsellor_id: cid, student: extra.student || tag(r), start: startIso, end: iso(ms(startIso) + mins * MIN),
    reason: extra.reason || REASONS[Math.floor(r() * REASONS.length)], first_visit: mins === FIRST_VISIT,
    status: extra.status || (ms(startIso) + mins * MIN < now ? (r() < 0.9 ? 'completed' : 'no_show') : 'active'),
    revealed: extra.revealed ?? r() < 0.2,
  });
  for (let d = -14; d <= 21; d++) {
    const day = addDays(today, d);
    if (weekday(day) > 5) continue;
    for (const t of ['09:00', '10:00', '11:15', '14:00', '15:30', '16:15']) if (r() < 0.5 || d < 0) book(1, atLocal(day, t), r() < 0.2 ? FIRST_VISIT : SESSION);
    const mehtaFull = d >= 0 && d <= 8;
    for (const t of ['10:00', '10:45', '11:30', '12:15', '13:00', '13:45', '14:30', '15:15']) if (mehtaFull || r() < 0.45) book(2, atLocal(day, t), SESSION);
  }
  // this student: one upcoming, one past, one cancelled
  const nextNoor = (() => { for (let d = 2; d < 10; d++) { const day = addDays(today, d); if (weekday(day) <= 5) return day; } return addDays(today, 3); })();
  s.bookings = s.bookings.filter((b) => !(b.counsellor_id === 1 && overlaps(ms(b.start), ms(b.end), ms(atLocal(nextNoor, '10:15')), ms(atLocal(nextNoor, '11:00')))));
  book(1, atLocal(nextNoor, '10:15'), SESSION, { student: ME, reason: 'academic_stress', status: 'active', revealed: false });
  book(1, atLocal(addDays(today, -9), '11:00'), FIRST_VISIT, { student: ME, reason: 'anxiety', status: 'completed', revealed: true });
  const cancelledDay = addDays(today, -17);
  s.bookings.push({ id: id++, counsellor_id: 2, student: ME, start: atLocal(cancelledDay, '15:30'), end: iso(ms(atLocal(cancelledDay, '15:30')) + SESSION * MIN), reason: 'sleep', first_visit: false, status: 'cancelled', revealed: false });

  // waitlist: this student waits in Dr Mehta's line, and holds an open offer from the any-counsellor line
  const mehtaLine = { id: id++, student: ME, counsellor_id: 2, urgent: false, joined_at: iso(now - 30 * HOUR), status: 'waiting', misses: 0, ahead: 2 };
  const anyLine = { id: id++, student: ME, counsellor_id: null, urgent: false, joined_at: iso(now - 50 * HOUR), status: 'offered', misses: 0, ahead: 0 };
  s.waitlist.push(mehtaLine, anyLine);
  const offerDay = (() => { for (let d = 1; d < 8; d++) { const day = addDays(today, d); if (weekday(day) <= 5) return day; } return addDays(today, 1); })();
  const offerStart = atLocal(offerDay, '14:30');
  s.bookings = s.bookings.filter((b) => !(b.counsellor_id === 2 && overlaps(ms(b.start), ms(b.end), ms(offerStart), ms(offerStart) + SESSION * MIN)));
  s.offers.push({ id: id++, entry_id: anyLine.id, counsellor_id: 2, start: offerStart, end: iso(ms(offerStart) + SESSION * MIN), expires_at: iso(now + 24 * MIN), status: 'open' });

  // events
  const ev = (d, t, mins, title, location, capacity, tags, taken, mine) => {
    const start = atLocal(addDays(today, d), t);
    s.events.push({ id: id++, title, start, end: iso(ms(start) + mins * MIN), location, capacity, tags, registered: taken, waitlisted: 0, mine: mine || null });
  };
  ev(1, '17:00', 60, 'Yoga', 'Sports hall', 20, ['mindfulness', 'sleep'], 14, 'registered');
  ev(4, '16:00', 90, 'Sleep before exams', 'Room 2.14', 24, ['sleep', 'exams'], 20, null);
  ev(6, '12:30', 45, 'Breathing for exam nerves', 'Library seminar room', 15, ['exams', 'mindfulness'], 15, null);
  ev(8, '17:00', 60, 'Yoga', 'Sports hall', 20, ['mindfulness'], 20, 'waitlisted');
  ev(11, '15:00', 60, 'Talking about low mood', 'Room 1.03', 18, ['low mood'], 6, null);
  ev(15, '17:00', 60, 'Yoga', 'Sports hall', 20, ['mindfulness', 'sleep'], 9, null);
  ev(19, '13:00', 60, 'Study habits that hold up', 'Room 2.14', 30, ['exams', 'study'], 11, null);
  s.events.find((e) => e.mine === 'waitlisted').waitlisted = 3;

  // inbox
  const note = (kind, title, body, ago, read, who = ME, payload = {}) => s.notifications.push({ id: id++, recipient: who, kind, title, body, payload, send_at: iso(now - ago), read });
  const offerName = 'Dr Mehta';
  note('offer', 'Time offered from the waitlist', `${offerName} can see you on ${new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Dubai', weekday: 'long', day: 'numeric', month: 'short' }).format(new Date(offerStart))} at 14:30. Accept within 30 minutes or it goes to the next person.`, 6 * MIN, false);
  note('event_reminder', 'Yoga tomorrow at 17:00', 'You are registered. Sports hall.', 3 * HOUR, false);
  note('announcement', 'Counselling hours over the winter break', 'Sessions run as usual until 23 December and start again on 4 January. The waitlist stays open.', 26 * HOUR, true);
  note('session_reminder', 'Session in 1 hour', 'Dr Noor at 11:00, first visit.', 9 * DAY + HOUR, true);
  note('notification', 'You joined Dr Mehta’s waitlist', 'You will get an offer when a time frees up.', 30 * HOUR, true);
  note('session_reminder', 'Session in 24 hours', `Dr Noor, ${new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Dubai', weekday: 'long' }).format(dubaiMidnight(nextNoor))} at 10:15.`, 5 * MIN, false, 'counsellor:1');
  note('announcement', 'Counselling hours over the winter break', 'Sessions run as usual until 23 December and start again on 4 January.', 26 * HOUR, true, 'counsellor:1');
  s.seq = id + 10;
  return s;
}

let S = null;
function state() {
  if (S) return S;
  try { const raw = sessionStorage.getItem(KEY); if (raw) S = JSON.parse(raw); } catch { /* private mode */ }
  if (!S) S = seed();
  return S;
}
function save() { try { sessionStorage.setItem(KEY, JSON.stringify(S)); } catch { /* full or blocked */ } }
const nextId = () => ++state().seq;

// --- a tiny event bus standing in for /api/stream ---------------------------------------------------------
const listeners = new Set();
const emit = (kind, data) => listeners.forEach((fn) => fn(kind, data));

let who = null; // { role, pseudonym?, counsellor_id?, display_name }
const recipient = () => (who?.role === 'C' ? 'counsellor:1' : ME);
const need = (...roles) => (!who ? fail(401, 'Sign in first') : roles.includes(who.role) ? null : fail(403, 'Not allowed for your role'));

// --- booking rules -------------------------------------------------------------------------------------------
function counsellor(id) { return state().counsellors.find((c) => c.id === Number(id)); }
function freeDay(cid, day, firstVisit) {
  const s = state();
  const len = (firstVisit ? FIRST_VISIT : SESSION) * MIN;
  const lo = dubaiMidnight(day).getTime(), hi = lo + DAY;
  const now = Date.now();
  const clip = (a) => ({ start: iso(Math.max(lo, ms(a.start))), end: iso(Math.min(hi, ms(a.end))) });
  const open = s.availability.filter((a) => a.counsellor_id === cid && a.kind === 'open' && overlaps(ms(a.start), ms(a.end), lo, hi)).map(clip);
  const held = s.offers.filter((o) => o.counsellor_id === cid && o.status === 'open' && ms(o.expires_at) > now);
  const busyRaw = [
    ...s.bookings.filter((b) => b.counsellor_id === cid && b.status === 'active'),
    ...s.availability.filter((a) => a.counsellor_id === cid && a.kind === 'blocked'),
    ...held,
  ].filter((b) => overlaps(ms(b.start), ms(b.end), lo, hi)).map(clip).sort((a, b) => ms(a.start) - ms(b.start));
  const busy = [];
  for (const b of busyRaw) { const last = busy[busy.length - 1]; if (last && ms(b.start) <= ms(last.end)) last.end = iso(Math.max(ms(last.end), ms(b.end))); else busy.push({ ...b }); }
  const starts = [];
  for (const w of open) {
    let t = Math.ceil(Math.max(ms(w.start), now + 15 * MIN) / (15 * MIN)) * 15 * MIN;
    for (; t + len <= ms(w.end); t += 15 * MIN) if (!busy.some((b) => overlaps(t, t + len, ms(b.start), ms(b.end)))) starts.push(iso(t));
  }
  return { counsellor_id: cid, day, session_minutes: len / MIN, open, busy, starts };
}
const hasFreeSoon = (cid) => { const today = isoDate(); for (let i = 0; i < 7; i++) if (freeDay(cid, addDays(today, i), false).starts.length) return true; return false; };
const bookingOut = (b) => ({ id: b.id, counsellor_id: b.counsellor_id, counsellor_name: counsellor(b.counsellor_id)?.display_name, start: b.start, end: b.end, reason: b.reason, first_visit: b.first_visit, status: b.status, revealed: b.revealed });
const sessionOut = (b) => ({ id: b.id, start: b.start, end: b.end, student: b.student, reason: b.reason, first_visit: b.first_visit, status: b.status, revealed: b.revealed, identity: null });

// offers lapse lazily: the first miss sends you back in line, the second removes you
function lapseOffers() {
  const s = state(), now = Date.now();
  for (const o of s.offers) {
    if (o.status !== 'open' || ms(o.expires_at) > now) continue;
    o.status = 'expired';
    const e = s.waitlist.find((x) => x.id === o.entry_id);
    if (!e) continue;
    e.misses += 1;
    if (e.misses >= 2) s.waitlist = s.waitlist.filter((x) => x !== e); else { e.status = 'waiting'; e.ahead = 1; }
  }
}
function entryOut(e) {
  const o = state().offers.find((x) => x.entry_id === e.id && x.status === 'open');
  return {
    id: e.id, counsellor_id: e.counsellor_id, counsellor_name: e.counsellor_id ? counsellor(e.counsellor_id)?.display_name : null,
    urgent: e.urgent, joined_at: e.joined_at, status: o ? 'offered' : 'waiting', misses: e.misses, ahead: e.ahead,
    offer: o ? { id: o.id, counsellor_id: o.counsellor_id, counsellor_name: counsellor(o.counsellor_id)?.display_name, start: o.start, end: o.end, expires_at: o.expires_at, status: o.status } : null,
  };
}
const eventOut = (e) => ({ id: e.id, title: e.title, start: e.start, end: e.end, location: e.location, capacity: e.capacity, tags: e.tags, registered: e.registered, waitlisted: e.waitlisted, spots_left: Math.max(0, e.capacity - e.registered), my_status: who?.role === 'S' ? e.mine : null });

export const demo = {
  mode: 'demo',
  /** Sign in as one of the three demo accounts: 'S' student, 'C' counsellor (Dr Noor), 'A' admin. */
  signInAs(role) {
    who = role === 'C' ? { account_id: 2, role: 'C', counsellor_id: 1, display_name: 'Dr Noor' }
      : role === 'A' ? { account_id: 3, role: 'A', display_name: 'Wellbeing team' }
        : { account_id: 1, role: 'S', pseudonym: ME, display_name: 'Student' };
    try { sessionStorage.setItem('wbh-demo-role', who.role); } catch { /* ignore */ }
    return wait(who);
  },
  restore() {
    let role = null;
    try { role = sessionStorage.getItem('wbh-demo-role'); } catch { /* ignore */ }
    return role ? this.signInAs(role) : Promise.resolve(null);
  },
  reset() { S = seed(); save(); },
  login: () => fail(400, 'Demo mode has no passwords: pick a demo account'),
  register: () => fail(400, 'Demo mode has no passwords: pick a demo account'),
  logout() { who = null; try { sessionStorage.removeItem('wbh-demo-role'); } catch { /* ignore */ } return wait(null); },
  me: () => (who ? wait(who) : fail(401, 'Not signed in')),
  health: () => wait({ status: 'ok' }),

  counsellors: () => need('S', 'C', 'A') || wait(state().counsellors),
  freeDays(cid, { date, days = 7, firstVisit = false } = {}) {
    const c = counsellor(cid);
    if (!c) return fail(404, 'Counsellor not found');
    lapseOffers();
    const first = date || isoDate();
    return wait(Array.from({ length: days }, (_, i) => freeDay(c.id, addDays(first, i), firstVisit)));
  },
  book({ counsellor_id, start, reason, first_visit = false, reveal = false }) {
    const denied = need('S'); if (denied) return denied;
    const c = counsellor(counsellor_id);
    if (!c) return fail(404, 'Counsellor not found');
    if (!REASONS.includes(reason)) return fail(422, 'Pick a reason');
    if (ms(start) > Date.now() + 60 * DAY) return fail(400, 'Sessions can be booked up to 60 days ahead');
    const day = isoDate(start);
    if (!freeDay(c.id, day, first_visit).starts.includes(iso(ms(start)))) return fail(409, 'That time was just taken. Pick another.');
    const b = { id: nextId(), counsellor_id: c.id, student: ME, start: iso(ms(start)), end: iso(ms(start) + (first_visit ? FIRST_VISIT : SESSION) * MIN), reason, first_visit, status: 'active', revealed: reveal };
    state().bookings.push(b); save();
    emit('slot_taken', { counsellor_id: c.id, start: b.start, end: b.end });
    return wait(bookingOut(b));
  },
  myBookings() { const d = need('S'); if (d) return d; return wait(state().bookings.filter((b) => b.student === ME).map(bookingOut)); },
  cancelBooking(id) {
    const d = need('S', 'C'); if (d) return d;
    const b = state().bookings.find((x) => x.id === Number(id) && (who.role === 'C' ? x.counsellor_id === 1 : x.student === ME));
    if (!b) return fail(404, 'Booking not found');
    if (b.status !== 'active') return fail(400, 'Only an upcoming session can be cancelled');
    if (ms(b.start) <= Date.now()) return fail(400, 'This session has already started');
    b.status = 'cancelled'; save();
    emit('slot_freed', { counsellor_id: b.counsellor_id, start: b.start, end: b.end });
    return wait(null);
  },
  availability(from, to) {
    const d = need('C'); if (d) return d;
    const lo = from ? ms(from) : Date.now(), hi = to ? ms(to) : lo + 14 * DAY;
    return wait(state().availability.filter((a) => a.counsellor_id === 1 && overlaps(ms(a.start), ms(a.end), lo, hi)).sort((a, b) => ms(a.start) - ms(b.start)).map(({ counsellor_id, ...a }) => a));
  },
  addAvailability({ start, end, kind = 'open', note = '' }) {
    const d = need('C'); if (d) return d;
    const a0 = ms(start), a1 = ms(end);
    if (!(a1 > a0)) return fail(400, 'The end must be after the start');
    if (a1 - a0 > DAY) return fail(400, 'A window can be 24 hours at most');
    if (a0 % (15 * MIN) || a1 % (15 * MIN)) return fail(400, 'Times go in quarter hours');
    const clash = state().availability.find((a) => a.counsellor_id === 1 && a.kind === kind && overlaps(ms(a.start), ms(a.end), a0, a1));
    if (clash) return fail(409, `It overlaps your ${kind === 'open' ? 'open hours' : 'blocked time'} on that day`);
    const row = { id: nextId(), counsellor_id: 1, start: iso(a0), end: iso(a1), kind, note };
    state().availability.push(row); save();
    const { counsellor_id, ...out } = row;
    return wait(out);
  },
  removeAvailability(id) {
    const d = need('C'); if (d) return d;
    const s = state(), a = s.availability.find((x) => x.id === Number(id) && x.counsellor_id === 1);
    if (!a) return fail(404, 'Availability not found');
    if (a.kind === 'open' && s.bookings.some((b) => b.counsellor_id === 1 && b.status === 'active' && overlaps(ms(b.start), ms(b.end), ms(a.start), ms(a.end)))) return fail(409, 'Sessions are booked in this window: cancel them first');
    s.availability = s.availability.filter((x) => x !== a); save();
    return wait(null);
  },
  sessionsOn(date) {
    const d = need('C'); if (d) return d;
    const lo = dubaiMidnight(date || isoDate()).getTime();
    return wait(state().bookings.filter((b) => b.counsellor_id === 1 && b.status !== 'cancelled' && ms(b.start) >= lo && ms(b.start) < lo + DAY).sort((a, b) => ms(a.start) - ms(b.start)).map(sessionOut));
  },
  markBooking(id, status) {
    const d = need('C'); if (d) return d;
    const b = state().bookings.find((x) => x.id === Number(id) && x.counsellor_id === 1);
    if (!b) return fail(404, 'Booking not found');
    if (ms(b.start) > Date.now()) return fail(400, 'This session has not started yet');
    b.status = status; save();
    return wait(sessionOut(b));
  },

  joinWaitlist({ counsellor_id = null, urgent = false }) {
    const d = need('S'); if (d) return d;
    const s = state();
    if (counsellor_id !== null && !counsellor(counsellor_id)) return fail(404, 'Counsellor not found');
    if (s.waitlist.some((e) => e.student === ME && e.counsellor_id === counsellor_id)) return fail(409, 'You are already in this line');
    const free = counsellor_id === null ? s.counsellors.some((c) => hasFreeSoon(c.id)) : hasFreeSoon(counsellor_id);
    if (free) return fail(409, counsellor_id === null ? 'A counsellor has free time in the next 7 days: book it instead' : `${counsellor(counsellor_id).display_name} has free time in the next 7 days: book it instead`);
    const e = { id: nextId(), student: ME, counsellor_id, urgent, joined_at: iso(Date.now()), status: 'waiting', misses: 0, ahead: urgent ? 0 : 3 };
    s.waitlist.push(e); save();
    return wait(entryOut(e));
  },
  myWaitlists() { const d = need('S'); if (d) return d; lapseOffers(); save(); return wait(state().waitlist.filter((e) => e.student === ME).map(entryOut)); },
  leaveWaitlist(id) {
    const d = need('S'); if (d) return d;
    const s = state(); const e = s.waitlist.find((x) => x.id === Number(id) && x.student === ME);
    if (!e) return fail(404, 'Waitlist entry not found');
    s.waitlist = s.waitlist.filter((x) => x !== e);
    s.offers.filter((o) => o.entry_id === e.id && o.status === 'open').forEach((o) => { o.status = 'declined'; });
    save(); return wait(null);
  },
  acceptOffer(id, { reason = 'other', reveal = false } = {}) {
    const d = need('S'); if (d) return d;
    lapseOffers();
    const s = state(); const o = s.offers.find((x) => x.id === Number(id));
    if (!o) return fail(404, 'Offer not found');
    if (o.status !== 'open') return fail(409, 'This offer has ended and the time went to the next person');
    o.status = 'accepted';
    const b = { id: nextId(), counsellor_id: o.counsellor_id, student: ME, start: o.start, end: o.end, reason, first_visit: false, status: 'active', revealed: reveal };
    s.bookings.push(b);
    s.waitlist = s.waitlist.filter((e) => e.student !== ME); // accepting leaves every other line
    save(); return wait(bookingOut(b));
  },
  declineOffer(id) {
    const d = need('S'); if (d) return d;
    const s = state(); const o = s.offers.find((x) => x.id === Number(id));
    if (!o) return fail(404, 'Offer not found');
    if (o.status !== 'open') return fail(409, 'This offer has already ended');
    o.status = 'declined';
    s.waitlist = s.waitlist.filter((e) => e.id !== o.entry_id);
    save(); return wait(null);
  },
  waitlistCounts() { const d = need('C'); if (d) return d; return wait({ urgent: 1, normal: 3, any_urgent: 0, any_normal: 6 }); },

  events({ from, to, tag: t } = {}) {
    const d = need('S', 'C', 'A'); if (d) return d;
    const lo = from ? ms(from) : Date.now(), hi = to ? ms(to) : lo + 31 * DAY;
    const want = t ? t.trim().toLowerCase() : null;
    return wait(state().events.filter((e) => ms(e.start) >= lo && ms(e.start) <= hi && (!want || e.tags.some((x) => x.toLowerCase() === want))).sort((a, b) => ms(a.start) - ms(b.start)).map(eventOut));
  },
  upcomingEvents(k = 5) { return this.events({}).then((list) => list.slice(0, k)); },
  createEvent({ title, start, end, location = '', capacity, tags = [] }) {
    const d = need('A'); if (d) return d;
    if (!title?.trim()) return fail(422, 'Write a title');
    if (!(ms(end) > ms(start))) return fail(400, 'The end must be after the start');
    if (!(capacity >= 1)) return fail(422, 'Capacity is at least 1');
    const e = { id: nextId(), title: title.trim(), start: iso(ms(start)), end: iso(ms(end)), location, capacity: Number(capacity), tags: tags.map((x) => x.trim().toLowerCase()).filter(Boolean), registered: 0, waitlisted: 0, mine: null };
    state().events.push(e); save(); return wait(eventOut(e));
  },
  updateEvent(id, body) {
    const d = need('A'); if (d) return d;
    const e = state().events.find((x) => x.id === Number(id));
    if (!e) return fail(404, 'Event not found');
    Object.assign(e, body); save(); return wait(eventOut(e));
  },
  deleteEvent(id) {
    const d = need('A'); if (d) return d;
    const s = state(); if (!s.events.some((x) => x.id === Number(id))) return fail(404, 'Event not found');
    s.events = s.events.filter((x) => x.id !== Number(id)); save(); return wait(null);
  },
  register(id) {
    const d = need('S'); if (d) return d;
    const e = state().events.find((x) => x.id === Number(id));
    if (!e) return fail(404, 'Event not found');
    if (e.mine) return fail(409, `You are ${e.mine}`);
    if (ms(e.start) < Date.now()) return fail(400, 'This event has already started');
    if (e.registered < e.capacity) { e.registered += 1; e.mine = 'registered'; } else { e.waitlisted += 1; e.mine = 'waitlisted'; }
    save(); return wait({ event_id: e.id, status: e.mine });
  },
  unregister(id) {
    const d = need('S'); if (d) return d;
    const e = state().events.find((x) => x.id === Number(id));
    if (!e || !e.mine) return fail(404, 'Not registered for this event');
    if (e.mine === 'registered') { if (e.waitlisted > 0) e.waitlisted -= 1; else e.registered -= 1; } else e.waitlisted -= 1;
    e.mine = null; save(); return wait(null);
  },

  notifications(limit = 50) {
    const d = need('S', 'C'); if (d) return d;
    const me = recipient();
    return wait(state().notifications.filter((n) => n.recipient === me || n.recipient === 'all').sort((a, b) => ms(b.send_at) - ms(a.send_at)).slice(0, limit).map(({ recipient: _r, ...n }) => n));
  },
  markRead(id) {
    const d = need('S', 'C'); if (d) return d;
    const n = state().notifications.find((x) => x.id === Number(id));
    if (!n) return fail(404, 'Notification not found');
    n.read = true; save(); return wait(null);
  },
  announce({ title, body = '', send_at = null }) {
    const d = need('A'); if (d) return d;
    if (!title?.trim()) return fail(422, 'Write a title');
    const when = send_at ? ms(send_at) : Date.now();
    const row = { id: nextId(), title: title.trim(), body, send_at: iso(when), status: when > Date.now() + MIN ? 'scheduled' : 'sent' };
    state().announcements.unshift(row);
    if (row.status === 'sent') {
      state().notifications.push({ id: nextId(), recipient: 'all', kind: 'announcement', title: row.title, body, payload: {}, send_at: row.send_at, read: false });
      emit('notification', { title: row.title });
    }
    save(); return wait(row);
  },
  announcements() { return wait(state().announcements); },
  deadLetters() { const d = need('A'); if (d) return d; return wait(state().deadLetters); },

  stream(onEvent) { listeners.add(onEvent); return () => listeners.delete(onEvent); },
};
