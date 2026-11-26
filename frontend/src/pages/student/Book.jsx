import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../api/index.js';
import * as T from '../../api/time.js';
import { useAsync } from '../../hooks/useAsync.js';
import { Icon } from '../../components/Icon.jsx';
import { Button, Card, ChipGroup, ErrorNote, PageHead, REASONS, Skeleton, Toggle, reasonLabel, useToast } from '../../components/ui.jsx';

const initials = (name) => name.replace(/^Dr\.? /, '').split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase();
const ANY = 'any';

/** The 7 free days of every counsellor from `from`, as { [id]: FreeDay[] }. */
function useAllFree(counsellors, from, firstVisit) {
  return useAsync(async () => {
    if (!counsellors?.length) return {};
    const lists = await Promise.all(counsellors.map((c) => api.freeDays(c.id, { date: from, days: 7, firstVisit })));
    return Object.fromEntries(counsellors.map((c, i) => [c.id, lists[i]]));
  }, [counsellors, from, firstVisit]);
}

export default function Book() {
  const toast = useToast();
  const today = T.isoDate();
  const counsellors = useAsync(() => api.counsellors(), []);
  const [cid, setCid] = useState(null);
  const [week, setWeek] = useState(0);
  const [firstVisit, setFirstVisit] = useState(false);
  const from = T.addDays(today, week * 7);
  const free = useAllFree(counsellors.data, from, firstVisit);
  const soon = useAllFree(counsellors.data, today, false); // "first free" on the cards and the waitlist rule: always from today
  const [day, setDay] = useState(null);
  const [pick, setPick] = useState(null);
  const [reason, setReason] = useState(null);
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [done, setDone] = useState(null);

  useEffect(() => { if (counsellors.data?.length && cid === null) setCid(counsellors.data[0].id); }, [counsellors.data, cid]);
  useEffect(() => { setPick(null); setErr(null); }, [cid, week, firstVisit]);

  const byName = useMemo(() => Object.fromEntries((counsellors.data || []).map((c) => [c.id, c])), [counsellors.data]);

  // the shown week: one counsellor's days, or every counsellor's merged for "any"
  const days = useMemo(() => {
    if (!free.data || cid === null) return null;
    const ids = cid === ANY ? Object.keys(free.data).map(Number) : [cid];
    return Array.from({ length: 7 }, (_, i) => {
      const iso = T.addDays(from, i);
      const starts = ids.flatMap((id) => (free.data[id]?.[i]?.starts || []).map((s) => ({ start: s, counsellor_id: id })))
        .sort((a, b) => new Date(a.start) - new Date(b.start));
      const open = ids.some((id) => (free.data[id]?.[i]?.open || []).length);
      return { iso, starts, open };
    });
  }, [free.data, cid, from]);

  useEffect(() => {
    if (!days) return;
    if (!day || !days.some((d) => d.iso === day)) setDay((days.find((d) => d.starts.length) || days[0]).iso);
  }, [days, day]);

  const firstFree = (id) => {
    const list = soon.data?.[id];
    for (const d of list || []) if (d.starts.length) return d.starts[0];
    return null;
  };
  const anyFirst = (counsellors.data || []).map((c) => ({ s: firstFree(c.id), c })).filter((x) => x.s).sort((a, b) => new Date(a.s) - new Date(b.s))[0];
  const noneThisWeek = soon.data && cid !== null && (cid === ANY ? !anyFirst : !firstFree(cid));

  const shown = days?.find((d) => d.iso === day);
  const groups = useMemo(() => {
    const g = { Morning: [], Afternoon: [], Evening: [] };
    for (const s of shown?.starts || []) {
      const h = Number(T.time(s.start).slice(0, 2));
      g[h < 12 ? 'Morning' : h < 17 ? 'Afternoon' : 'Evening'].push(s);
    }
    return Object.entries(g).filter(([, xs]) => xs.length);
  }, [shown]);

  const minutes = firstVisit ? 60 : 45;
  async function book() {
    if (!reason) { setErr('Pick the reason closest to why you are booking'); document.getElementById('reason-first')?.focus(); return; }
    setBusy(true); setErr(null);
    try {
      const b = await api.book({ counsellor_id: pick.counsellor_id, start: pick.start, reason, first_visit: firstVisit, reveal });
      setDone(b); toast('Session booked');
      free.reload(); soon.reload();
    } catch (e) {
      setErr(e.message);
      if (e.status === 409) { setPick(null); free.reload(); }
    } finally { setBusy(false); }
  }

  if (done) {
    return (
      <>
        <PageHead title="Book a session" />
        <Card className="booked">
          <span className="booked__icon"><Icon name="check" size={22} /></span>
          <div className="booked__text">
            <h2>You are booked with {done.counsellor_name}</h2>
            <p className="booked__when">{T.longDay(done.start)}, {T.span(done.start, done.end)}</p>
            <p>{reasonLabel(done.reason)}{done.first_visit ? ' · first visit, 60 minutes' : ''} · {done.revealed ? 'your name is shared for this session' : 'your counsellor sees your tag only'}</p>
            <p className="muted">Reminders arrive 24 hours and 1 hour before, in your inbox.</p>
          </div>
          <div className="booked__acts">
            <Link className="btn btn--primary" to="/sessions"><span>See my sessions</span></Link>
            <Button variant="secondary" onClick={() => { setDone(null); setPick(null); setReason(null); setReveal(false); }}>Book another</Button>
          </div>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHead title="Book a session" sub="Pick a counsellor and a start time. All times are Dubai time." />
      <ErrorNote error={counsellors.error || free.error} onRetry={() => { counsellors.reload(); free.reload(); }} />
      <div className="book">
        <div className="book__who" role="radiogroup" aria-label="Counsellor">
          {!counsellors.data ? <Skeleton rows={3} height={76} /> : (
            <>
              {counsellors.data.map((c) => {
                const f = firstFree(c.id);
                return (
                  <button key={c.id} type="button" role="radio" aria-checked={cid === c.id} className={`who${cid === c.id ? ' is-on' : ''}`} onClick={() => { setCid(c.id); setWeek(0); }}>
                    <span className="avatar">{initials(c.display_name)}</span>
                    <span className="who__text">
                      <b>{c.display_name}</b>
                      <span className="who__tags">{c.specialties.map((s) => <i key={s}>{s}</i>)}</span>
                      <span className="who__free">{!soon.data ? 'Checking free times' : f ? `First free: ${T.day(f)}, ${T.time(f)}` : 'No free time in the next 7 days'}</span>
                    </span>
                  </button>
                );
              })}
              <button type="button" role="radio" aria-checked={cid === ANY} className={`who${cid === ANY ? ' is-on' : ''}`} onClick={() => { setCid(ANY); setWeek(0); }}>
                <span className="avatar avatar--any"><Icon name="users" /></span>
                <span className="who__text">
                  <b>Any counsellor</b>
                  <span className="who__free">{!soon.data ? 'Checking free times' : anyFirst ? `First free: ${T.day(anyFirst.s)}, ${T.time(anyFirst.s)} with ${anyFirst.c.display_name}` : 'No free time in the next 7 days'}</span>
                </span>
              </button>
            </>
          )}
        </div>

        <div className="book__when">
          {noneThisWeek && week === 0 ? (
            <JoinWaitlist cid={cid} name={cid === ANY ? null : byName[cid]?.display_name} onWeekAfter={() => setWeek(1)} />
          ) : (
            <Card className="slots">
              <div className="slots__head">
                <div className="weeknav">
                  <button type="button" className="icon-btn" onClick={() => setWeek((w) => w - 1)} disabled={week === 0} aria-label="Previous week"><Icon name="left" /></button>
                  <b>{week === 0 ? 'Next 7 days' : `${T.day(T.dubaiMidnight(from))} to ${T.day(T.dubaiMidnight(T.addDays(from, 6)))}`}</b>
                  <button type="button" className="icon-btn" onClick={() => setWeek((w) => w + 1)} disabled={week >= 7} aria-label="Next week"><Icon name="right" /></button>
                </div>
                <Toggle label="First visit" hint={`${minutes} minutes`} checked={firstVisit} onChange={setFirstVisit} />
              </div>

              <div className="days" role="tablist" aria-label="Day">
                {(days || Array.from({ length: 7 }, (_, i) => ({ iso: T.addDays(from, i), starts: null }))).map((d) => {
                  const at = T.dubaiMidnight(d.iso);
                  const n = d.starts?.length;
                  return (
                    <button key={d.iso} type="button" role="tab" aria-selected={day === d.iso} className={`day${day === d.iso ? ' is-on' : ''}${n === 0 ? ' is-empty' : ''}`} onClick={() => { setDay(d.iso); setPick(null); }}>
                      <span>{d.iso === today ? 'Today' : T.weekday(at)}</span>
                      <b>{T.dateNum(at)}</b>
                      <em>{n === null || n === undefined ? '·' : n > 0 ? `${n} free` : d.open ? 'Full' : 'Closed'}</em>
                    </button>
                  );
                })}
              </div>

              <div className="times" role="tabpanel" aria-label={shown ? T.longDay(T.dubaiMidnight(shown.iso)) : 'Times'}>
                {free.loading && !days ? <Skeleton rows={2} height={40} /> : !shown?.starts.length ? (
                  <p className="times__none">{shown && !shown.open ? `No counselling hours on ${T.longDay(T.dubaiMidnight(shown.iso))}.` : `Every start time on ${shown ? T.longDay(T.dubaiMidnight(shown.iso)) : 'this day'} is taken.`} Try another day{week === 0 ? ' or the next week' : ''}.</p>
                ) : groups.map(([label, xs]) => (
                  <div key={label} className="times__group">
                    <p className="t-label">{label}</p>
                    <div className="times__row">
                      {xs.map((s) => {
                        const on = pick?.start === s.start && pick?.counsellor_id === s.counsellor_id;
                        return (
                          <button key={`${s.counsellor_id}-${s.start}`} type="button" className={`time${on ? ' is-on' : ''}`} aria-pressed={on} onClick={() => { setPick(s); setErr(null); }}>
                            {T.time(s.start)}{cid === ANY ? <i>{initials(byName[s.counsellor_id]?.display_name || '')}</i> : null}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {pick ? (
            <Card className="confirm-card" aria-label="Your booking">
              <div className="confirm-card__sum">
                <span className="date-tile"><b>{T.dateNum(pick.start)}</b><i>{T.month(pick.start)}</i></span>
                <div>
                  <h2>{T.longDay(pick.start)}, {T.span(pick.start, new Date(new Date(pick.start).getTime() + minutes * 60_000))}</h2>
                  <p>{byName[pick.counsellor_id]?.display_name} · {minutes} minutes{firstVisit ? ', first visit' : ''}</p>
                </div>
              </div>
              <div id="reason-first">
                <ChipGroup label="Reason" options={REASONS} value={reason} onChange={(r) => { setReason(r); setErr(null); }} />
              </div>
              <Toggle label={`Share my name with ${byName[pick.counsellor_id]?.display_name}`} hint={reveal ? 'They see your name for this session only' : `Off: they see ${'your tag'} and the reason`} checked={reveal} onChange={setReveal} />
              {err ? <p className="field__error" role="alert">{err}</p> : null}
              <div className="confirm-card__acts">
                <Button onClick={book} busy={busy} icon="check">Book {T.time(pick.start)}</Button>
                <Button variant="quiet" onClick={() => setPick(null)}>Pick another time</Button>
              </div>
            </Card>
          ) : err ? <p className="field__error" role="alert">{err}</p> : null}
        </div>
      </div>
    </>
  );
}

function JoinWaitlist({ cid, name, onWeekAfter }) {
  const toast = useToast();
  const [urgent, setUrgent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [joined, setJoined] = useState(null);
  const line = name ? `${name}’s waitlist` : 'the waitlist for any counsellor';
  async function join() {
    setBusy(true); setErr(null);
    try { const e = await api.joinWaitlist({ counsellor_id: cid === ANY ? null : cid, urgent }); setJoined(e); toast(`You joined ${line}`); }
    catch (e) { setErr(e.message); } finally { setBusy(false); }
  }
  if (joined) {
    return (
      <Card className="waitjoin">
        <span className="booked__icon"><Icon name="check" size={20} /></span>
        <h2>You are in {line}</h2>
        <p>{joined.ahead === 0 ? 'You are first in line.' : `${joined.ahead} ${joined.ahead === 1 ? 'student is' : 'students are'} ahead of you.`} When a session frees up you get an offer and 30 minutes to take it.</p>
        <Link className="btn btn--secondary" to="/waitlist"><span>See my waitlists</span></Link>
      </Card>
    );
  }
  return (
    <Card className="waitjoin">
      <span className="empty__icon"><Icon name="clock" size={20} /></span>
      <h2>{name ? `${name} is booked for the next 7 days` : 'Every counsellor is booked for the next 7 days'}</h2>
      <p>Join {line}. When someone cancels, the first student in line is offered the time and has 30 minutes to accept. Waiting more than 72 hours moves you up.</p>
      <Toggle label="I need to talk to someone within 48 hours" hint="Urgent requests are offered time first" checked={urgent} onChange={setUrgent} />
      {err ? <p className="field__error" role="alert">{err}</p> : null}
      <div className="confirm-card__acts">
        <Button onClick={join} busy={busy}>Join {name ? `${name}’s waitlist` : 'the waitlist'}</Button>
        <Button variant="quiet" onClick={onWeekAfter}>See the week after</Button>
      </div>
    </Card>
  );
}

