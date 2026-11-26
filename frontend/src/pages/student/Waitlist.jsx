import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../api/index.js';
import * as T from '../../api/time.js';
import { useAsync, useNow } from '../../hooks/useAsync.js';
import { Icon } from '../../components/Icon.jsx';
import { Badge, Button, Card, ChipGroup, Confirm, Empty, ErrorNote, PageHead, REASONS, Skeleton, Toggle, useToast } from '../../components/ui.jsx';

function Countdown({ until, now }) {
  const left = Math.max(0, new Date(until) - now);
  const m = Math.floor(left / 60_000), s = Math.floor((left % 60_000) / 1000);
  return <span className="countdown" aria-label={`${m} minutes left`}>{m}:{String(s).padStart(2, '0')}</span>;
}

function Offer({ entry, onDone }) {
  const toast = useToast();
  const now = useNow(1000);
  const o = entry.offer;
  const [reason, setReason] = useState('other');
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);
  const lapsed = new Date(o.expires_at) <= now;
  async function act(kind) {
    setBusy(kind); setErr(null);
    try {
      if (kind === 'accept') { await api.acceptOffer(o.id, { reason, reveal }); toast(`Booked with ${o.counsellor_name}`); }
      else { await api.declineOffer(o.id); toast('Offer declined. The time goes to the next student.'); }
      onDone(kind);
    } catch (e) { setErr(e.message); setBusy(null); }
  }
  return (
    <Card className="offer" aria-label="Offer">
      <div className="offer__head">
        <span className="offer__pulse" aria-hidden="true" />
        <p className="t-label">Time offered from {entry.counsellor_id ? `${entry.counsellor_name}’s line` : 'the any-counsellor line'}</p>
        <span className="offer__left">{lapsed ? 'Ended' : <>Accept within <Countdown until={o.expires_at} now={now} /></>}</span>
      </div>
      <div className="confirm-card__sum">
        <span className="date-tile date-tile--lg"><b>{T.dateNum(o.start)}</b><i>{T.month(o.start)}</i></span>
        <div><h2>{T.longDay(o.start)}, {T.span(o.start, o.end)}</h2><p>{o.counsellor_name} · 45 minutes</p></div>
      </div>
      <ChipGroup label="Reason" options={REASONS} value={reason} onChange={setReason} />
      <Toggle label={`Share my name with ${o.counsellor_name}`} hint="For this session only" checked={reveal} onChange={setReveal} />
      {err ? <p className="field__error" role="alert">{err}</p> : null}
      <p className="muted small">Accepting books this time and takes you out of every other line.</p>
      <div className="confirm-card__acts">
        <Button onClick={() => act('accept')} busy={busy === 'accept'} disabled={lapsed || !!busy} icon="check">Accept the time</Button>
        <Button variant="secondary" onClick={() => act('decline')} busy={busy === 'decline'} disabled={lapsed || !!busy}>Decline</Button>
      </div>
    </Card>
  );
}

export default function Waitlist() {
  const toast = useToast();
  const list = useAsync(() => api.myWaitlists(), []);
  const counsellors = useAsync(() => api.counsellors(), []);
  const [cid, setCid] = useState('');
  const [urgent, setUrgent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const offers = (list.data || []).filter((e) => e.offer);
  const waiting = (list.data || []).filter((e) => !e.offer);
  const taken = new Set((list.data || []).map((e) => e.counsellor_id ?? 'any'));

  async function join(e) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      await api.joinWaitlist({ counsellor_id: cid === 'any' || cid === '' ? null : Number(cid), urgent });
      toast('You joined the line'); setCid(''); setUrgent(false); list.reload();
    } catch (x) { setErr(x.message); } finally { setBusy(false); }
  }
  async function leave(entry) {
    try { await api.leaveWaitlist(entry.id); list.setData((xs) => xs.filter((x) => x.id !== entry.id)); toast('You left the line'); }
    catch (x) { toast(x.message, 'error'); }
  }

  return (
    <>
      <PageHead title="Waitlist" sub="When a counsellor has no free time in the next 7 days, wait in their line. Freed times are offered in order." />
      <ErrorNote error={list.error} onRetry={list.reload} />
      {offers.map((e) => <Offer key={e.offer.id} entry={e} onDone={() => list.reload()} />)}

      <div className="split-2">
        <section aria-labelledby="lines-h">
          <h2 id="lines-h" className="h-sub">Your lines</h2>
          {list.loading && !list.data ? <Skeleton rows={2} height={76} /> : !waiting.length && !offers.length ? (
            <Empty icon="clock" title="You are not waiting in any line">Lines open when a counsellor is booked for the next 7 days. <Link to="/book">Book a session</Link> first.</Empty>
          ) : (
            <ul className="rows-list">
              {waiting.map((e) => (
                <li key={e.id} className="row">
                  <span className={`avatar${e.counsellor_id ? '' : ' avatar--any'}`}>{e.counsellor_id ? e.counsellor_name.replace(/^Dr /, '').slice(0, 2).toUpperCase() : <Icon name="users" />}</span>
                  <div className="row__main">
                    <b>{e.counsellor_id ? `${e.counsellor_name}’s line` : 'Any counsellor'}</b>
                    <span>{e.ahead === 0 ? 'You are next' : `${e.ahead} ${e.ahead === 1 ? 'student' : 'students'} ahead of you`} · joined {T.relative(e.joined_at)}{e.misses ? ` · ${e.misses} offer missed` : ''}</span>
                  </div>
                  <div className="row__side">
                    {e.urgent ? <Badge tone="warn">Urgent</Badge> : <Badge>Waiting</Badge>}
                    <Confirm confirmLabel="Leave line" onConfirm={() => leave(e)}>{(ask) => <button type="button" className="text-btn" onClick={ask}>Leave</button>}</Confirm>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <Card as="form" className="join-card" onSubmit={join} aria-labelledby="join-h">
          <h2 id="join-h" className="h-sub">Join a line</h2>
          <div className="field">
            <label className="field__label" htmlFor="wl-who">Counsellor</label>
            <select id="wl-who" value={cid} onChange={(e) => setCid(e.target.value)}>
              <option value="">Any counsellor</option>
              {(counsellors.data || []).map((c) => <option key={c.id} value={c.id} disabled={taken.has(c.id)}>{c.display_name}{taken.has(c.id) ? ' (already waiting)' : ''}</option>)}
            </select>
          </div>
          <Toggle label="I need to talk to someone within 48 hours" hint="Urgent requests are offered time first" checked={urgent} onChange={setUrgent} />
          {err ? <p className="field__error" role="alert">{err}</p> : null}
          <Button type="submit" busy={busy} variant="secondary">Join the line</Button>
          <p className="muted small">Miss one offer and you keep your place. Miss a second and you leave that line.</p>
        </Card>
      </div>
    </>
  );
}
