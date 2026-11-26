import { useEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { api, demo } from '../api/index.js';
import { useSession } from '../session.jsx';
import { Icon, Mark } from './Icon.jsx';
import { useToast } from './ui.jsx';

const NAV = {
  S: [['/book', 'Book', 'calendar'], ['/sessions', 'My sessions', 'list'], ['/waitlist', 'Waitlist', 'clock'], ['/workshops', 'Workshops', 'workshop'], ['/inbox', 'Inbox', 'inbox']],
  C: [['/today', 'Sessions', 'list'], ['/hours', 'Open hours', 'hours'], ['/workshops', 'Workshops', 'workshop'], ['/inbox', 'Inbox', 'inbox']],
  A: [['/manage', 'Workshops', 'workshop'], ['/announce', 'Announcements', 'megaphone'], ['/deliveries', 'Failed deliveries', 'alert']],
};
const ROLE = { S: 'Student', C: 'Counsellor', A: 'Wellbeing team' };

/** Unread count for the Inbox, refreshed on the live stream and every minute. */
function useUnread(enabled) {
  const [n, setN] = useState(0);
  const toast = useToast();
  useEffect(() => {
    if (!enabled) return undefined;
    let alive = true;
    const load = () => api.notifications(50).then((xs) => { if (alive) setN(xs.filter((x) => !x.read).length); }).catch(() => {});
    load();
    const t = setInterval(load, 60_000);
    const stop = api.stream((kind, data) => {
      if (kind === 'offer') toast('A time was offered to you from the waitlist');
      else if (kind === 'reminder' && data?.title) toast(data.title);
      if (kind !== 'slot_taken' && kind !== 'slot_freed') load();
    });
    const onRead = () => load();
    window.addEventListener('wbh:inbox', onRead);
    return () => { alive = false; clearInterval(t); stop(); window.removeEventListener('wbh:inbox', onRead); };
  }, [enabled, toast]);
  return n;
}

export function Shell({ children }) {
  const { user, mode, signOut } = useSession();
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  useEffect(() => setOpen(false), [loc.pathname]);
  const unread = useUnread(user.role === 'S' || user.role === 'C');
  const items = NAV[user.role] || [];
  const who = user.role === 'S' ? user.pseudonym : user.display_name;

  return (
    <div className={`shell${open ? ' is-open' : ''}`}>
      <a className="skip" href="#main">Skip to content</a>
      <aside className="side" aria-label="App">
        <a className="side__brand" href="/" aria-label="Well-Being Hub home page"><Mark /><span>Well-Being Hub</span></a>
        <nav className="side__nav" aria-label="Main">
          {items.map(([to, label, icon]) => (
            <NavLink key={to} to={to} className={({ isActive }) => `side__link${isActive ? ' is-on' : ''}`}>
              <Icon name={icon} /><span>{label}</span>
              {to === '/inbox' && unread ? <em className="side__count" aria-label={`${unread} unread`}>{unread}</em> : null}
            </NavLink>
          ))}
        </nav>
        <div className="side__foot">
          {mode === 'demo' ? (
            <div className="side__demo"><Icon name="spark" /><span>Demo data, nothing is sent</span>
              <button type="button" className="text-btn" onClick={() => { demo.reset(); window.location.reload(); }}>Reset</button>
            </div>
          ) : null}
          <div className="side__me">
            <span className={`avatar${user.role === 'S' ? ' avatar--tag' : ''}`}>{user.role === 'S' ? user.pseudonym?.slice(1, 3) : (user.display_name || '?').replace(/^Dr /, '').slice(0, 1)}</span>
            <span className="side__who"><b className={user.role === 'S' ? 'mono' : ''}>{who}</b><span>{ROLE[user.role]}</span></span>
            <button type="button" className="icon-btn" onClick={signOut} aria-label="Sign out" title="Sign out"><Icon name="out" /></button>
          </div>
        </div>
      </aside>
      <header className="topbar">
        <a className="side__brand" href="/" aria-label="Well-Being Hub home page"><Mark /><span>Well-Being Hub</span></a>
        <button type="button" className="icon-btn" aria-expanded={open} aria-label="Menu" onClick={() => setOpen((o) => !o)}><Icon name={open ? 'x' : 'menu'} size={18} /></button>
      </header>
      <main id="main" className="main" tabIndex={-1}>{children}</main>
      <nav className="tabbar" aria-label="Main">
        {items.slice(0, 5).map(([to, label, icon]) => (
          <NavLink key={to} to={to} className={({ isActive }) => `tabbar__link${isActive ? ' is-on' : ''}`}>
            <span className="tabbar__icon"><Icon name={icon} size={18} />{to === '/inbox' && unread ? <i aria-label={`${unread} unread`} /> : null}</span>
            <span>{label.replace('My sessions', 'Sessions').replace('Failed deliveries', 'Failed')}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
