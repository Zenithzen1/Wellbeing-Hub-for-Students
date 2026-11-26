import { Link } from 'react-router-dom';
import { api } from '../api/index.js';
import * as T from '../api/time.js';
import { useAsync } from '../hooks/useAsync.js';
import { useSession } from '../session.jsx';
import { Icon } from '../components/Icon.jsx';
import { Button, Empty, ErrorNote, PageHead, Skeleton, useToast } from '../components/ui.jsx';

const KIND = {
  offer: ['clock', 'Waitlist offer'], session_reminder: ['calendar', 'Reminder'], event_reminder: ['workshop', 'Workshop'],
  announcement: ['megaphone', 'Announcement'], notification: ['bell', 'Update'],
};

export default function Inbox() {
  const { user } = useSession();
  const toast = useToast();
  const list = useAsync(() => api.notifications(50), []);
  const unread = (list.data || []).filter((n) => !n.read);

  async function read(n) {
    if (n.read) return;
    list.setData((xs) => xs.map((x) => (x.id === n.id ? { ...x, read: true } : x)));
    try { await api.markRead(n.id); window.dispatchEvent(new Event('wbh:inbox')); } catch { /* shown read either way */ }
  }
  async function readAll() {
    await Promise.all(unread.map((n) => api.markRead(n.id).catch(() => {})));
    list.setData((xs) => xs.map((x) => ({ ...x, read: true })));
    window.dispatchEvent(new Event('wbh:inbox'));
    toast('All marked as read');
  }

  return (
    <>
      <PageHead title="Inbox" sub="Reminders, waitlist offers and announcements. New ones arrive while the page is open.">
        {unread.length ? <Button variant="secondary" icon="check" onClick={readAll}>Mark all read</Button> : null}
      </PageHead>
      <ErrorNote error={list.error} onRetry={list.reload} />
      {list.loading && !list.data ? <Skeleton rows={4} height={72} /> : !list.data?.length ? (
        <Empty icon="inbox" title="Nothing yet">Reminders arrive 24 hours and 1 hour before each session.</Empty>
      ) : (
        <ul className="inbox">
          {list.data.map((n) => {
            const [icon, label] = KIND[n.kind] || KIND.notification;
            return (
              <li key={n.id}>
                <button type="button" className={`note${n.read ? '' : ' is-unread'}`} onClick={() => read(n)} aria-label={`${n.read ? '' : 'Unread. '}${n.title}`}>
                  <span className={`note__icon note__icon--${n.kind}`}><Icon name={icon} /></span>
                  <span className="note__text">
                    <span className="note__top"><b>{n.title}</b><time dateTime={n.send_at}>{T.relative(n.send_at)}</time></span>
                    <span className="note__body">{n.body}</span>
                    <span className="note__kind">{label}</span>
                  </span>
                  {n.read ? null : <i className="note__dot" aria-hidden="true" />}
                </button>
                {n.kind === 'offer' && user.role === 'S' ? <Link className="note__link" to="/waitlist">Answer the offer <Icon name="arrow" size={14} /></Link> : null}
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
