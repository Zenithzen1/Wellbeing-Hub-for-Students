import { useMemo, useState } from 'react';
import { api } from '../../api/index.js';
import * as T from '../../api/time.js';
import { useAsync } from '../../hooks/useAsync.js';
import { Icon } from '../../components/Icon.jsx';
import { Badge, Button, Card, Confirm, Empty, ErrorNote, Field, PageHead, Segmented, Skeleton, useToast } from '../../components/ui.jsx';

const quarter = (v) => /^\d{2}:(00|15|30|45)$/.test(v);

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
                      <Badge tone={a.kind === 'open' ? 'ok' : 'plain'}>{a.kind === 'open' ? 'Open' : 'Blocked'}</Badge>
                      <Confirm confirmLabel="Remove" onConfirm={() => remove(a)}>{(ask) => <button type="button" className="icon-btn" aria-label="Remove" onClick={ask}><Icon name="trash" /></button>}</Confirm>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>

        <Card as="form" className="join-card sticky" onSubmit={add} noValidate aria-labelledby="add-h">
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
    </>
  );
}
