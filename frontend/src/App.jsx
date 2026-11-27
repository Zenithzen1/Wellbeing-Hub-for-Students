import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { HOME, useSession } from './session.jsx';
import { Shell } from './components/Shell.jsx';
import SignIn from './pages/SignIn.jsx';
import Book from './pages/student/Book.jsx';
import Sessions from './pages/student/Sessions.jsx';
import Waitlist from './pages/student/Waitlist.jsx';
import Workshops from './pages/Workshops.jsx';
import Inbox from './pages/Inbox.jsx';
import Today from './pages/counsellor/Today.jsx';
import Hours from './pages/counsellor/Hours.jsx';
import { Announce, Deliveries, Manage } from './pages/admin/Admin.jsx';
import { Mark } from './components/Icon.jsx';
import { Button } from './components/ui.jsx';

// which roles may open each route ("S" student, "C" counsellor, "A" wellbeing team)
const ROUTES = [
  ['/book', Book, 'S'], ['/sessions', Sessions, 'S'], ['/waitlist', Waitlist, 'S'],
  ['/workshops', Workshops, 'SC'], ['/inbox', Inbox, 'SC'],
  ['/today', Today, 'C'], ['/hours', Hours, 'C'],
  ['/manage', Manage, 'A'], ['/announce', Announce, 'A'], ['/deliveries', Deliveries, 'A'],
];

export default function App() {
  const { user } = useSession();
  const loc = useLocation();
  if (user === undefined) return <div className="boot" aria-busy="true"><span className="spin" /></div>;
  if (!user) {
    return (
      <Routes>
        <Route path="/signin" element={<SignIn />} />
        <Route path="*" element={<Navigate to="/signin" replace state={{ from: loc.pathname }} />} />
      </Routes>
    );
  }
  const home = HOME[user.role];
  if (!home) return <NoScreens />; // the custodian ("K") has no screens in this app yet
  return (
    <Shell>
      <Routes>
        {ROUTES.map(([path, Page, roles]) => (
          <Route key={path} path={path} element={roles.includes(user.role) ? <Page /> : <Navigate to={home} replace />} />
        ))}
        <Route path="*" element={<Navigate to={home} replace />} />
      </Routes>
    </Shell>
  );
}

function NoScreens() {
  const { signOut } = useSession();
  return (
    <div className="boot">
      <div className="empty" style={{ maxWidth: 480, background: 'var(--surface)' }}>
        <Mark />
        <h3>This account has no screens here yet</h3>
        <p>The app has screens for students, counsellors and the wellbeing team.</p>
        <Button variant="secondary" onClick={signOut}>Sign out</Button>
      </div>
    </div>
  );
}
