import { useState } from 'react';
import { api } from '../../api/index.js';
import * as T from '../../api/time.js';
import { useAsync, useNow } from '../../hooks/useAsync.js';
import { Icon } from '../../components/Icon.jsx';
import { Badge, Button, Card, Confirm, Empty, ErrorNote, PageHead, Skeleton, reasonLabel, useToast } from '../../components/ui.jsx';

const STATUS = { active: ['Booked', 'accent'], completed: ['Completed', 'ok'], no_show: ['No-show', 'warn'], cancelled: ['Cancelled', 'plain'] };

export default function Today() {
  const toast = useToast();
  const now = useNow(30_000);
  const today = T.isoDate();
  const [date, setDate] = useState(today);
  const list = useAsync(() => api.sessionsOn(date), [date]);
  const counts = useAsync(() => api.waitlistCounts(), []);
  const [busy, setBusy] = useState(null);

  async function mark(s, status) {
    setBusy(`${s.id}-${status}`);
    try { const row = await api.markBooking(s.id, status); list.setData((xs) => xs.map((x) => (x.id === s.id ? row : x))); toast(status === 'completed' ? 'Marked completed' : 'Marked as a no-show'); }
    catch (e) { toast(e.message, 'error'); } finally { setBusy(null); }
  }
  async function cancel(s) {
    try { await api.cancelBooking(s.id); list.setData((xs) => xs.map((x) => (x.id === s.id ? { ...x, status: 'cancelled' } : x))); toast('Session cancelled. The time is offered to the waitlist.'); }
    catch (e) { toast(e.message, 'error'); }
  }

  const xs = list.data || [];
  const c = counts.data;
  return (
    <>
      <PageHead title="Sessions" sub="Each student shows as a tag and the reason they picked, with a name only when they shared it." />
      <div className="dateline">
        <button type="button" className="icon-btn" onClick={() => setDate(T.addDays(date, -1))} aria-label="Previous day"><Icon name="left" /></button>
        <h2>{date === today ? 'Today, ' : ''}{T.longDay(T.dubaiMidnight(date))}</h2>
        <button type="button" className="icon-btn" onClick={() => setDate(T.addDays(date, 1))} aria-label="Next day"><Icon name="right" /></button>
        {date !== today ? <Button variant="quiet" size="sm" onClick={() => setDate(today)}>Back to today</Button> : null}
      </div>

      <div className="stats">
        <Card className="stat"><span>Sessions</span><b>{xs.filter((s) => s.status !== 'cancelled').length}</b></Card>
        <Card className="stat"><span>First visits</span><b>{xs.filter((s) => s.first_visit && s.status !== 'cancelled').length}</b></Card>
        <Card className="stat"><span>Waiting for you</span><b>{c ? c.urgent + c.normal : '·'}</b>{c?.urgent ? <em>{c.urgent} urgent</em> : null}</Card>
        <Card className="stat"><span>Waiting for anyone</span><b>{c ? c.any_urgent + c.any_normal : '·'}</b>{c?.any_urgent ? <em>{c.any_urgent} urgent</em> : null}</Card>
      </div>

      <ErrorNote error={list.error} onRetry={list.reload} />
      {list.loading && !list.data ? <Skeleton rows={4} height={76} /> : !xs.length ? (
        <Empty icon="calendar" title="No sessions this day">Students book the start times your open hours leave free.</Empty>
      ) : (
        <ul className="rows-list sessions">
          {xs.map((s) => {
            const [label, tone] = STATUS[s.status] || [s.status, 'plain'];
            const started = new Date(s.start) <= now;
            return (
              <li key={s.id} className={`row${s.status === 'cancelled' ? ' is-muted' : ''}`}>
                <span className="row__time"><b>{T.time(s.start)}</b><span>{T.time(s.end)}</span></span>
                <span className="avatar avatar--tag">{s.student.slice(1, 3)}</span>
                <div className="row__main">
                  <b className="mono">{s.student}{s.revealed ? <span className="row__name"> · {s.identity || 'name shared'}</span> : null}</b>
                  <span>{reasonLabel(s.reason)}{s.first_visit ? ' · first visit, 60 minutes' : ''}</span>
                </div>
                <div className="row__side">
                  <Badge tone={tone}>{label}</Badge>
                  {s.status === 'active' && started ? (
                    <>
                      <Button size="sm" variant="secondary" busy={busy === `${s.id}-completed`} onClick={() => mark(s, 'completed')}>Completed</Button>
                      <Button size="sm" variant="quiet" busy={busy === `${s.id}-no_show`} onClick={() => mark(s, 'no_show')}>No-show</Button>
                    </>
                  ) : s.status === 'active' ? (
                    <Confirm confirmLabel="Cancel session" onConfirm={() => cancel(s)}>{(ask) => <button type="button" className="text-btn" onClick={ask}>Cancel</button>}</Confirm>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
