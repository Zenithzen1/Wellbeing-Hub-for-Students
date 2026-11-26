import { useState } from 'react';
import { api } from '../../api/index.js';
import * as T from '../../api/time.js';
import { useAsync } from '../../hooks/useAsync.js';
import { Icon } from '../../components/Icon.jsx';
import { Places } from '../Workshops.jsx';
import { Badge, Button, Card, Confirm, Empty, ErrorNote, Field, PageHead, Skeleton, Toggle, useToast } from '../../components/ui.jsx';

export function Manage() {
  const toast = useToast();
  const today = T.isoDate();
  const list = useAsync(() => api.events({}), []);
  const blank = { title: '', date: T.addDays(today, 7), start: '17:00', end: '18:00', location: '', capacity: '20', tags: '' };
  const [f, setF] = useState(blank);
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));

  async function create(e) {
    e.preventDefault();
    const errs = {};
    if (!f.title.trim()) errs.title = 'Write the workshop’s name';
    if (!f.date || f.date < today) errs.date = 'Pick today or a later day';
    if (f.end <= f.start) errs.end = 'The end must be after the start';
    if (!(Number(f.capacity) >= 1)) errs.capacity = 'Write how many places, as a number';
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      await api.createEvent({ title: f.title, start: T.atLocal(f.date, f.start), end: T.atLocal(f.date, f.end), location: f.location, capacity: Number(f.capacity), tags: f.tags.split(',').map((t) => t.trim()).filter(Boolean) });
      toast(`${f.title} posted`); setF(blank); list.reload();
    } catch (x) { setErrors({ form: x.message }); } finally { setBusy(false); }
  }
  async function remove(ev) {
    try { await api.deleteEvent(ev.id); list.setData((xs) => xs.filter((x) => x.id !== ev.id)); toast(`${ev.title} removed`); }
    catch (x) { toast(x.message, 'error'); }
  }

  return (
    <>
      <PageHead title="Workshops" sub="Post a workshop with a date, a room and a number of places. Students get a reminder 1 hour before." />
      <div className="split-2 split-2--form">
        <section aria-label="Posted workshops">
          <ErrorNote error={list.error} onRetry={list.reload} />
          {list.loading && !list.data ? <Skeleton rows={4} height={80} /> : !list.data?.length ? <Empty icon="workshop" title="No workshops posted">Post the first one with the form.</Empty> : (
            <ul className="events">
              {list.data.map((ev) => (
                <li key={ev.id} className="event">
                  <span className="date-tile date-tile--lg"><b>{T.dateNum(ev.start)}</b><i>{T.month(ev.start)}</i></span>
                  <div className="event__main">
                    <h3>{ev.title}</h3>
                    <p>{T.weekday(ev.start)} {T.span(ev.start, ev.end)}{ev.location ? ` · ${ev.location}` : ''}</p>
                    <div className="event__tags">{ev.tags.map((t) => <i key={t}>{t}</i>)}</div>
                  </div>
                  <div className="event__side">
                    <Places e={ev} />
                    <div className="event__act"><Confirm confirmLabel="Delete workshop" onConfirm={() => remove(ev)}>{(ask) => <button type="button" className="text-btn" onClick={ask}>Delete</button>}</Confirm></div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
        <Card as="form" className="join-card sticky" onSubmit={create} noValidate aria-labelledby="new-h">
          <h2 id="new-h" className="h-sub">Post a workshop</h2>
          <Field label="Name" id="w-title" error={errors.title}><input id="w-title" type="text" maxLength={200} value={f.title} onChange={set('title')} /></Field>
          <Field label="Day" id="w-date" error={errors.date}><input id="w-date" type="date" min={today} value={f.date} onChange={set('date')} /></Field>
          <div className="field-pair">
            <Field label="From" id="w-start"><input id="w-start" type="time" step="900" value={f.start} onChange={set('start')} /></Field>
            <Field label="To" id="w-end" error={errors.end}><input id="w-end" type="time" step="900" value={f.end} onChange={set('end')} /></Field>
          </div>
          <div className="field-pair">
            <Field label="Room" id="w-loc"><input id="w-loc" type="text" maxLength={200} value={f.location} onChange={set('location')} /></Field>
            <Field label="Places" id="w-cap" error={errors.capacity}><input id="w-cap" type="text" inputMode="numeric" value={f.capacity} onChange={set('capacity')} /></Field>
          </div>
          <Field label="Tags" id="w-tags" hint="Separated by commas: sleep, exams"><input id="w-tags" type="text" value={f.tags} onChange={set('tags')} /></Field>
          {errors.form ? <p className="field__error" role="alert">{errors.form}</p> : null}
          <Button type="submit" busy={busy}>Post the workshop</Button>
        </Card>
      </div>
    </>
  );
}

export function Announce() {
  const toast = useToast();
  const [f, setF] = useState({ title: '', body: '', later: false, date: T.addDays(T.isoDate(), 1), time: '09:00' });
  const [sent, setSent] = useState([]);
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  async function send(e) {
    e.preventDefault();
    if (!f.title.trim()) { setErrors({ title: 'Write a title students will see in their inbox' }); return; }
    setErrors({}); setBusy(true);
    try {
      const row = await api.announce({ title: f.title, body: f.body, send_at: f.later ? T.atLocal(f.date, f.time) : null });
      setSent((xs) => [row, ...xs]); toast(row.status === 'scheduled' ? 'Announcement scheduled' : 'Announcement sent');
      setF((x) => ({ ...x, title: '', body: '' }));
    } catch (x) { setErrors({ form: x.message }); } finally { setBusy(false); }
  }
  return (
    <>
      <PageHead title="Announcements" sub="A message to every student and counsellor, now or at a time you set. It lands in their inbox and any open tab." />
      <div className="split-2 split-2--form">
        <section aria-label="Sent this visit">
          {!sent.length ? <Empty icon="megaphone" title="Nothing sent yet">Announcements you send show here with when they go out.</Empty> : (
            <ul className="rows-list">
              {sent.map((a) => (
                <li key={a.id} className="row">
                  <span className="kind kind--open"><Icon name="megaphone" /></span>
                  <div className="row__main"><b>{a.title}</b><span>{T.day(a.send_at)}, {T.time(a.send_at)}</span></div>
                  <div className="row__side"><Badge tone={a.status === 'scheduled' ? 'accent' : 'ok'}>{a.status === 'scheduled' ? 'Scheduled' : 'Sent'}</Badge></div>
                </li>
              ))}
            </ul>
          )}
        </section>
        <Card as="form" className="join-card sticky" onSubmit={send} noValidate aria-labelledby="ann-h">
          <h2 id="ann-h" className="h-sub">New announcement</h2>
          <Field label="Title" id="a-title" error={errors.title}><input id="a-title" type="text" maxLength={200} value={f.title} onChange={(e) => setF((x) => ({ ...x, title: e.target.value }))} /></Field>
          <Field label="Message" id="a-body"><textarea id="a-body" rows={5} maxLength={5000} value={f.body} onChange={(e) => setF((x) => ({ ...x, body: e.target.value }))} /></Field>
          <Toggle label="Send later" hint={f.later ? 'At the day and time below, Dubai time' : 'Off: it goes out now'} checked={f.later} onChange={(v) => setF((x) => ({ ...x, later: v }))} />
          {f.later ? (
            <div className="field-pair">
              <Field label="Day" id="a-date"><input id="a-date" type="date" value={f.date} onChange={(e) => setF((x) => ({ ...x, date: e.target.value }))} /></Field>
              <Field label="Time" id="a-time"><input id="a-time" type="time" step="900" value={f.time} onChange={(e) => setF((x) => ({ ...x, time: e.target.value }))} /></Field>
            </div>
          ) : null}
          {errors.form ? <p className="field__error" role="alert">{errors.form}</p> : null}
          <Button type="submit" busy={busy} icon="send">{f.later ? 'Schedule announcement' : 'Send announcement'}</Button>
        </Card>
      </div>
    </>
  );
}

export function Deliveries() {
  const list = useAsync(() => api.deadLetters(), []);
  return (
    <>
      <PageHead title="Failed deliveries" sub="Messages whose delivery failed 4 times. Retries run after 1, 5 and 25 minutes before a message lands here." />
      <ErrorNote error={list.error} onRetry={list.reload} />
      {list.loading && !list.data ? <Skeleton rows={2} height={72} /> : !list.data?.length ? (
        <Empty icon="check" title="Every message was delivered">Nothing has failed 4 times.</Empty>
      ) : (
        <Card className="table-card">
          <table className="table">
            <thead><tr><th scope="col">Message</th><th scope="col">Channel</th><th scope="col">Attempts</th><th scope="col">Last try</th><th scope="col">Error</th></tr></thead>
            <tbody>
              {list.data.map((d) => (
                <tr key={d.id}><td><b>{d.title}</b></td><td>{d.kind}</td><td>{d.attempts}</td><td>{T.relative(d.last_attempt_at)}</td><td className="mono small">{d.last_error || '·'}</td></tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
