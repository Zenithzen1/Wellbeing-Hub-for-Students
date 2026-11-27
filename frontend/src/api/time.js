// Every time from the API is UTC; the hub shows Dubai time (UTC+4, no daylight saving), as the
// backend's clock.py does. Dates sent as ?date= are Dubai-time dates (YYYY-MM-DD).

export const TZ = 'Asia/Dubai';
export const OFFSET = '+04:00';
const HOUR = 3600_000;

const fmt = (opts) => new Intl.DateTimeFormat('en-GB', { timeZone: TZ, ...opts });
const fTime = fmt({ hour: '2-digit', minute: '2-digit', hour12: false });
const fDay = fmt({ weekday: 'short', day: 'numeric', month: 'short' });
const fLong = fmt({ weekday: 'long', day: 'numeric', month: 'long' });
const fWeekday = fmt({ weekday: 'short' });
const fDate = fmt({ day: 'numeric' });
const fMonth = fmt({ month: 'short' });
const fIso = fmt({ year: 'numeric', month: '2-digit', day: '2-digit' });

export const time = (d) => fTime.format(new Date(d));
export const day = (d) => fDay.format(new Date(d));
export const longDay = (d) => fLong.format(new Date(d));
export const weekday = (d) => fWeekday.format(new Date(d));
export const dateNum = (d) => fDate.format(new Date(d));
export const month = (d) => fMonth.format(new Date(d));
export const span = (a, b) => `${time(a)} to ${time(b)}`;

/** Dubai-time date of an instant, as YYYY-MM-DD. */
export function isoDate(d = new Date()) {
  const parts = Object.fromEntries(fIso.formatToParts(new Date(d)).map((p) => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

/** Midnight of a Dubai date ("2026-12-01") as an instant. */
export const dubaiMidnight = (iso) => new Date(`${iso}T00:00:00${OFFSET}`);

/** A Dubai date plus n days. */
export function addDays(iso, n) {
  return isoDate(new Date(dubaiMidnight(iso).getTime() + n * 24 * HOUR + 12 * HOUR));
}

/** "2026-12-01" + "10:15" -> "2026-12-01T10:15:00+04:00" (what the API expects). */
export const atLocal = (iso, hhmm) => `${iso}T${hhmm}:00${OFFSET}`;

/** "in 25 minutes", "3 hours ago". */
export function relative(d, now = Date.now()) {
  const diff = new Date(d).getTime() - now;
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });
  if (abs < 60_000) return 'just now';
  if (abs < HOUR) return rtf.format(Math.round(diff / 60_000), 'minute');
  if (abs < 24 * HOUR) return rtf.format(Math.round(diff / HOUR), 'hour');
  return rtf.format(Math.round(diff / (24 * HOUR)), 'day');
}

export const minutesBetween = (a, b) => Math.round((new Date(b) - new Date(a)) / 60_000);

/** 0 = Monday ... 6 = Sunday, for a Dubai date. */
export const weekdayIndex = (iso) => (new Date(dubaiMidnight(iso).getTime() + 12 * HOUR).getUTCDay() + 6) % 7;
/** The Monday of the week a Dubai date falls in. */
export const mondayOf = (iso) => addDays(iso, -weekdayIndex(iso));
