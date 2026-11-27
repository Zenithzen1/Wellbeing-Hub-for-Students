import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api/index.js';
import * as T from '../../api/time.js';
import { useAsync } from '../../hooks/useAsync.js';
import { Icon } from '../../components/Icon.jsx';
import { Button, Card, Confirm, Empty, ErrorNote, Field, PageHead, Segmented, Skeleton, useToast } from '../../components/ui.jsx';

const quarter = (v) => /^\d{2}:(00|15|30|45)$/.test(v);

/** This month at a glance: a dot under days with open hours, a ring on today; a day picks the form's date. */
function MonthGlance({ rows, today, value, onPick }) {
  const [month, setMonth] = useState(value.slice(0, 7)); // "2026-11"
  useEffect(() => setMonth(value.slice(0, 7)), [value]);
  const [y, m] = month.split('-').map(Number);
  const first = `${month}-01`;
  const shift = (n) => { const d = new Date(Date.UTC(y, m - 1 + n, 1)); setMonth(`${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`); };
  const days = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const lead = T.weekdayIndex(first);
  const kinds = new Map();
  for (const a of rows || []) { const d = T.isoDate(a.start); const k = kinds.get(d) || new Set(); k.add(a.kind); kinds.set(d, k); }
  const cells = [...Array(lead).fill(null), ...Array.from({ length: days }, (_, i) => T.addDays(first, i))];
  return (
    <Card className="month" aria-label="This month">
      <div className="month__head">
        <button type="button" className="icon-btn" onClick={() => shift(-1)} disabled={month <= today.slice(0, 7)} aria-label="Previous month"><Icon name="left" /></button>
        <b>{new Intl.DateTimeFormat('en-GB', { month: 'long', year: 'numeric', timeZone: T.TZ }).format(T.dubaiMidnight(first))}</b>
        <button type="button" className="icon-btn" onClick={() => shift(1)} aria-label="Next month"><Icon name="right" /></button>
      </div>
      <div className="month__dow" aria-hidden="true">{['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'].map((d) => <span key={d}>{d}</span>)}</div>
      <div className="month__days">
        {cells.map((d, i) => {
          if (!d) return <span key={`x${i}`} />;
          const k = kinds.get(d);
          const past = d < today;
          return (
            <button key={d} type="button" disabled={past} onClick={() => onPick(d)} aria-pressed={value === d}
              className={`mday${d === today ? ' is-today' : ''}${value === d ? ' is-on' : ''}`} aria-label={`${T.longDay(T.dubaiMidnight(d))}${k?.has('open') ? ', open hours' : ''}${k?.has('blocked') ? ', blocked time' : ''}`}>
              {Number(d.slice(8))}
              <span className="mday__dots">{k?.has('open') ? <i className="dot dot--open" /> : null}{k?.has('blocked') ? <i className="dot dot--blocked" /> : null}</span>
            </button>
          );
        })}
      </div>
      <p className="month__key"><i className="dot dot--open" />Open hours <i className="dot dot--blocked" />Blocked time</p>
    </Card>
  );
}

export default function Hours() {
  const toast = useToast();
  const today = T.isoDate();
  const from = T.dubaiMidnight(today).toISOString();
  const to = T.dubaiMidnight(T.addDays(today, 14)).toISOString();
  const list = useAsync(() => api.availability(from, to), []);
  const [form, setForm] = useState({ date: T.addDays(today, 1), start: '09:00', end: '13:00', kind: 'open', note: '' });
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target ? e.target.value : e }));

  const byDay = useMemo(() => {
    const m = new Map();
    for (const a of list.data || []) { const d = T.isoDate(a.start); if (!m.has(d)) m.set(d, []); m.get(d).push(a); }
    return [...m.entries()];
  }, [list.data]);

  async function add(e) {
    e.preventDefault();
    const errs = {};
    if (!/^\d{4}-\d{2}-\d{2}$/.test(form.date) || form.date < today) errs.date = 'Pick today or a later day';
    if (!quarter(form.start)) errs.start = 'Use a quarter hour, such as 09:00 or 09:15';
    if (!quarter(form.end)) errs.end = 'Use a quarter hour, such as 13:00 or 13:45';
    else if (form.end <= form.start) errs.end = 'The end must be after the start';
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      const row = await api.addAvailability({ start: T.atLocal(form.date, form.start), end: T.atLocal(form.date, form.end), kind: form.kind, note: form.note });
      list.setData((xs) => [...(xs || []), row].sort((a, b) => new Date(a.start) - new Date(b.start)));
      toast(form.kind === 'open' ? 'Open hours published' : 'Time blocked');
    } catch (x) { setErrors({ form: x.message }); } finally { setBusy(false); }
  }
  async function remove(a) {
    try { await api.removeAvailability(a.id); list.setData((xs) => xs.filter((x) => x.id !== a.id)); toast('Removed'); }
    catch (x) { toast(x.message, 'error'); }
  }

  return (
    <>
      <PageHead title="Open hours" sub="Publish the hours students can book, or block time. Sessions start on the quarter hour." />
      <div className="split-2 split-2--form">
        <section aria-label="The next 14 days">
          <ErrorNote error={list.error} onRetry={list.reload} />
          {list.loading && !list.data ? <Skeleton rows={4} height={64} /> : !byDay.length ? (
            <Empty icon="hours" title="No hours in the next 14 days">Students see no free times until you publish open hours.</Empty>
          ) : byDay.map(([d, xs]) => (
            <div key={d} className="hours-day">
              <h2 className="h-sub">{d === today ? 'Today, ' : ''}{T.longDay(T.dubaiMidnight(d))}</h2>
              <ul className="rows-list">
                {xs.map((a) => (
                  <li key={a.id} className="row">
                    <span className={`kind kind--${a.kind}`}><Icon name={a.kind === 'open' ? 'hours' : 'block'} /></span>
                    <div className="row__main"><b>{T.span(a.start, a.end)}</b><span>{a.kind === 'open' ? 'Open for bookings' : `Blocked${a.note ? `: ${a.note}` : ''}`}</span></div>
                    <div className="row__side">
                      <Confirm confirmLabel="Remove" onConfirm={() => remove(a)}>{(ask) => <button type="button" className="icon-btn" aria-label="Remove" onClick={ask}><Icon name="trash" /></button>}</Confirm>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>

        <div className="side-col sticky">
        <MonthGlance rows={list.data} today={today} value={form.date} onPick={(d) => setForm((f) => ({ ...f, date: d }))} />
        <Card as="form" className="join-card" onSubmit={add} noValidate aria-labelledby="add-h">
          <h2 id="add-h" className="h-sub">Add hours</h2>
          <Segmented label="Kind" value={form.kind} onChange={set('kind')} options={[['open', 'Open'], ['blocked', 'Blocked']]} />
          <Field label="Day" id="h-date" error={errors.date}><input id="h-date" type="date" min={today} value={form.date} onChange={set('date')} /></Field>
          <div className="field-pair">
            <Field label="From" id="h-start" error={errors.start}><input id="h-start" type="time" step="900" value={form.start} onChange={set('start')} /></Field>
            <Field label="To" id="h-end" error={errors.end}><input id="h-end" type="time" step="900" value={form.end} onChange={set('end')} /></Field>
          </div>
          {form.kind === 'blocked' ? <Field label="Note" id="h-note" hint="Only you see it"><input id="h-note" type="text" maxLength={200} value={form.note} onChange={set('note')} /></Field> : null}
          {errors.form ? <p className="field__error" role="alert">{errors.form}</p> : null}
          <Button type="submit" busy={busy}>{form.kind === 'open' ? 'Publish open hours' : 'Block this time'}</Button>
          <p className="muted small">Times are Dubai time. A window is 24 hours at most.</p>
        </Card>
        </div>
      </div>
    </>
  );
}
