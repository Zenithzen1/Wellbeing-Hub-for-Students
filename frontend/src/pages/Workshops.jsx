import { useMemo, useState } from 'react';
import { api } from '../api/index.js';
import * as T from '../api/time.js';
import { useAsync } from '../hooks/useAsync.js';
import { useSession } from '../session.jsx';
import { Icon } from '../components/Icon.jsx';
import { Badge, Button, Empty, ErrorNote, PageHead, Skeleton, useToast } from '../components/ui.jsx';

export function Places({ e }) {
  const k = Math.min(1, e.registered / e.capacity);
  return (
    <div className="places" aria-label={`${e.registered} of ${e.capacity} places taken`}>
      <span className="places__bar"><i style={{ width: `${k * 100}%` }} /></span>
      <span className="places__text">{e.spots_left ? `${e.spots_left} of ${e.capacity} places left` : `Full${e.waitlisted ? ` · ${e.waitlisted} waiting` : ''}`}</span>
    </div>
  );
}

export default function Workshops() {
  const { user } = useSession();
  const toast = useToast();
  const [tag, setTag] = useState('');
  const all = useAsync(() => api.events({}), []);
  const [busy, setBusy] = useState(null);

  const tags = useMemo(() => [...new Set((all.data || []).flatMap((e) => e.tags.map((t) => t.toLowerCase())))].sort(), [all.data]);
  const list = useMemo(() => (all.data || []).filter((e) => !tag || e.tags.map((t) => t.toLowerCase()).includes(tag)), [all.data, tag]);
  const weeks = useMemo(() => {
    const out = [];
    for (const e of list) {
      const monday = T.mondayOf(T.isoDate(e.start));
      const last = out[out.length - 1];
      if (last && last.monday === monday) last.items.push(e); else out.push({ monday, items: [e] });
    }
    return out;
  }, [list]);

  async function act(e) {
    setBusy(e.id);
    try {
      if (e.my_status) { await api.unregister(e.id); toast(e.my_status === 'registered' ? `You left ${e.title}` : `You left the line for ${e.title}`); }
      else { const r = await api.register(e.id); toast(r.status === 'registered' ? `You are registered for ${e.title}` : `${e.title} is full: you joined its line`); }
      await all.reload();
    } catch (x) { toast(x.message, 'error'); } finally { setBusy(null); }
  }

  const student = user.role === 'S';
  return (
    <>
      <PageHead title="Workshops" sub={student ? 'Register in one tap. When a workshop is full you join its line and get the next free place.' : 'Workshops in the next 31 days and how full they are.'} />
      <ErrorNote error={all.error} onRetry={all.reload} />
      {tags.length ? (
        <div className="filter" role="group" aria-label="Filter by tag">
          <button type="button" className={`chip${!tag ? ' is-on' : ''}`} aria-pressed={!tag} onClick={() => setTag('')}>All</button>
          {tags.map((t) => <button key={t} type="button" className={`chip${tag === t ? ' is-on' : ''}`} aria-pressed={tag === t} onClick={() => setTag(t)}>{t}</button>)}
        </div>
      ) : null}
      {all.loading && !all.data ? <Skeleton rows={4} height={96} /> : !list.length ? (
        <Empty icon="workshop" title="No workshops in the next 31 days">{tag ? `Nothing tagged ${tag}. Try All.` : 'New workshops show here as soon as staff post them.'}</Empty>
      ) : weeks.map((w) => (
        <section key={w.monday} className="week" aria-label={`Week of ${T.day(T.dubaiMidnight(w.monday))}`}>
          <h2 className="h-sub">Week of {T.day(T.dubaiMidnight(w.monday))}</h2>
          <ul className="events">
            {w.items.map((e) => (
              <li key={e.id} className={`event${e.my_status ? ` is-${e.my_status}` : ''}`}>
                <span className="date-tile date-tile--lg"><b>{T.dateNum(e.start)}</b><i>{T.month(e.start)}</i></span>
                <div className="event__main">
                  <h3>{e.title}</h3>
                  <p>{T.weekday(e.start)} {T.span(e.start, e.end)}{e.location ? ` · ${e.location}` : ''}</p>
                  <div className="event__tags">{e.tags.map((t) => <i key={t}>{t}</i>)}</div>
                </div>
                <div className="event__side">
                  <Places e={e} />
                  {student ? (
                    <div className="event__act">
                      {e.my_status === 'registered' ? <Badge tone="ok"><Icon name="check" size={12} />Registered</Badge> : e.my_status === 'waitlisted' ? <Badge tone="warn">In line</Badge> : null}
                      <Button size="sm" variant={e.my_status ? 'quiet' : e.spots_left ? 'primary' : 'secondary'} busy={busy === e.id} onClick={() => act(e)}>
                        {e.my_status === 'registered' ? 'Leave' : e.my_status === 'waitlisted' ? 'Leave the line' : e.spots_left ? 'Register' : 'Join the line'}
                      </Button>
                    </div>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </>
  );
}
