import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { HOME, useSession } from '../session.jsx';
import { Icon, Mark } from '../components/Icon.jsx';
import { Button, Field } from '../components/ui.jsx';

const DEMOS = [
  ['S', 'Student', 'Book Dr Noor, answer a waitlist offer, sign up for Yoga', 'calendar'],
  ['C', 'Counsellor', 'Dr Noor’s sessions, open hours and waitlist counts', 'list'],
  ['A', 'Wellbeing team', 'Post workshops, send announcements', 'megaphone'],
];

export default function SignIn() {
  const { signIn, signInDemo } = useSession();
  const nav = useNavigate();
  const from = useLocation().state?.from;
  const after = (u) => nav(from && from !== '/signin' ? from : HOME[u.role] || '/book', { replace: true });
  const [create, setCreate] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState({});
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(null);

  async function submit(e) {
    e.preventDefault();
    const errs = {};
    if (!/^\S+@\S+\.\S+$/.test(email)) errs.email = 'Write your university email, with an @';
    if (password.length < 8) errs.password = 'Write a password of 8 characters or more';
    setErrors(errs);
    if (Object.keys(errs).length) { setStatus(`${Object.keys(errs).length} field${Object.keys(errs).length > 1 ? 's' : ''} to fix`); document.getElementById(Object.keys(errs)[0] === 'email' ? 'si-email' : 'si-pass')?.focus(); return; }
    setBusy('live'); setStatus('Signing in');
    try {
      const u = await signIn(email, password, { create });
      after(u);
    } catch (err) {
      setStatus(err.status === 401 || err.status === 400 ? err.message : err.status === 404 || err.status === 405 || err.status >= 500 || err.status === undefined
        ? 'Sign-in is not switched on in the backend yet. Use a demo account below.' : err.message);
    } finally { setBusy(null); }
  }

  async function demo(role) {
    setBusy(role);
    const u = await signInDemo(role);
    after(u);
  }

  return (
    <div className="signin">
      <div className="signin__panel">
        <a className="side__brand" href="/"><Mark /><span>Well-Being Hub</span></a>
        <div className="signin__head">
          <h1>{create ? 'Create your account' : 'Sign in'}</h1>
          <p>Your email becomes a tag such as <span className="mono">#47C32E</span>. Counsellors see the tag, not your name.</p>
        </div>
        <form className="form" onSubmit={submit} noValidate>
          <Field label="University email" id="si-email" error={errors.email}>
            <input id="si-email" type="email" autoComplete="email" inputMode="email" value={email} onChange={(e) => setEmail(e.target.value)} aria-invalid={!!errors.email} aria-describedby={errors.email ? 'si-email-err' : undefined} />
          </Field>
          <Field label="Password" id="si-pass" error={errors.password}>
            <input id="si-pass" type="password" autoComplete={create ? 'new-password' : 'current-password'} value={password} onChange={(e) => setPassword(e.target.value)} aria-invalid={!!errors.password} aria-describedby={errors.password ? 'si-pass-err' : undefined} />
          </Field>
          <Button type="submit" busy={busy === 'live'} className="btn--block">{create ? 'Create account' : 'Sign in'}</Button>
          <p className="form__status" role="status">{status}</p>
          <button type="button" className="link-btn" onClick={() => { setCreate((c) => !c); setStatus(''); }}>
            {create ? 'I already have an account' : 'New here? Create an account'}
          </button>
        </form>
      </div>
      <div className="signin__demo">
        <div className="signin__demo-head">
          <h2>Try it with demo data</h2>
          <p>Runs in your browser with sample counsellors and workshops. Nothing is sent to the server.</p>
        </div>
        <ul className="demo-list">
          {DEMOS.map(([role, title, line, icon]) => (
            <li key={role}>
              <button type="button" className="demo-card" onClick={() => demo(role)} disabled={!!busy}>
                <span className="demo-card__icon"><Icon name={icon} size={18} /></span>
                <span className="demo-card__text"><b>{title}</b><span>{line}</span></span>
                {busy === role ? <span className="spin" aria-hidden="true" /> : <Icon name="arrow" className="demo-card__go" />}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
