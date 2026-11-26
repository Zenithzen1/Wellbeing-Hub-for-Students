import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../api/index.js';
import * as T from '../../api/time.js';
import { useAsync, useNow } from '../../hooks/useAsync.js';
import { Badge, Card, Confirm, Empty, ErrorNote, PageHead, Segmented, Skeleton, reasonLabel, useToast } from '../../components/ui.jsx';

const STATUS = { active: ['Upcoming', 'accent'], completed: ['Completed', 'ok'], cancelled: ['Cancelled', 'plain'], no_show: ['Missed', 'warn'] };

export default function Sessions() {
  const toast = useToast();
  const now = useNow(60_000);
  const list = useAsync(() => api.myBookings(), []);
  const [tab, setTab] = useState('upcoming');

  const { upcoming, past } = useMemo(() => {
    const xs = list.data || [];
    const up = xs.filter((b) => b.status === 'active' && new Date(b.end) > now).sort((a, b) => new Date(a.start) - new Date(b.start));
    const pa = xs.filter((b) => !up.includes(b)).sort((a, b) => new Date(b.start) - new Date(a.start));
    return { upcoming: up, past: pa };
  }, [list.data, now]);
  const shown = tab === 'upcoming' ? upcoming : past;
  const next = upcoming[0];

  async function cancel(b) {
    try {
      await api.cancelBooking(b.id);
      list.setData((xs) => xs.map((x) => (x.id === b.id ? { ...x, status: 'cancelled' } : x)));
      toast('Session cancelled. The time goes to the waitlist first.');
    } catch (e) { toast(e.message, 'error'); }
  }

  return (
    <>
      <PageHead title="My sessions" sub="Upcoming and past sessions with their counsellor, reason and time.">
        <Link className="btn btn--primary" to="/book"><span>Book a session</span></Link>
      </PageHead>
      <ErrorNote error={list.error} onRetry={list.reload} />

      {next ? (
        <Card className="next">
          <span className="date-tile date-tile--lg"><b>{T.dateNum(next.start)}</b><i>{T.month(next.start)}</i></span>
          <div className="next__text">
            <p className="t-label">Next session · {T.relative(next.start, now)}</p>
            <h2>{T.longDay(next.start)}, {T.span(next.start, next.end)}</h2>
            <p>{next.counsellor_name} · {reasonLabel(next.reason)}{next.first_visit ? ' · first visit' : ''} · {next.revealed ? 'name shared' : 'tag only'}</p>
          </div>
        </Card>
      ) : null}

      <Segmented label="Sessions" value={tab} onChange={setTab} options={[['upcoming', 'Upcoming', upcoming.length], ['past', 'Past and cancelled', past.length]]} />

      {list.loading && !list.data ? <Skeleton rows={3} height={84} /> : !shown.length ? (
        <Empty icon="calendar" title={tab === 'upcoming' ? 'No upcoming sessions' : 'Nothing here yet'} action={tab === 'upcoming' ? <Link className="btn btn--secondary" to="/book"><span>Book a session</span></Link> : null}>
          {tab === 'upcoming' ? 'Book a 45-minute session, or 60 minutes for your first visit.' : 'Sessions you have had or cancelled show here.'}
        </Empty>
      ) : (
        <ul className="rows-list">
          {shown.map((b) => {
            const [label, tone] = STATUS[b.status] || [b.status, 'plain'];
            return (
              <li key={b.id} className={`row${b.status === 'cancelled' ? ' is-muted' : ''}`}>
                <span className="date-tile"><b>{T.dateNum(b.start)}</b><i>{T.month(b.start)}</i></span>
                <div className="row__main">
                  <b>{T.span(b.start, b.end)} <span className="muted">· {T.weekday(b.start)}</span></b>
                  <span>{b.counsellor_name} · {reasonLabel(b.reason)}{b.first_visit ? ' · first visit' : ''}</span>
                </div>
                <div className="row__side">
                  {b.revealed ? <Badge>Name shared</Badge> : null}
                  <Badge tone={tone}>{label}</Badge>
                  {b.status === 'active' && new Date(b.start) > now ? (
                    <Confirm confirmLabel="Cancel session" busyLabel="Cancelling" onConfirm={() => cancel(b)}>
                      {(ask) => <button type="button" className="text-btn" onClick={ask}>Cancel</button>}
                    </Confirm>
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
