import { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from 'react';
import { Icon } from './Icon.jsx';

export const REASONS = [
  ['academic_stress', 'Academic stress'], ['anxiety', 'Anxiety'], ['low_mood', 'Low mood'],
  ['relationships', 'Relationships'], ['sleep', 'Sleep'], ['other', 'Other'],
];
export const reasonLabel = (r) => (REASONS.find(([k]) => k === r)?.[1] || r?.replace(/_/g, ' ') || '');

export function Button({ variant = 'primary', size, icon, busy, children, className = '', ...rest }) {
  return (
    <button type="button" className={`btn btn--${variant}${size ? ` btn--${size}` : ''} ${className}`} disabled={busy || rest.disabled} aria-busy={busy || undefined} {...rest}>
      {icon ? <Icon name={icon} /> : null}
      <span>{children}</span>
      {busy ? <span className="spin" aria-hidden="true" /> : null}
    </button>
  );
}

export function Toggle({ label, hint, checked, onChange, disabled }) {
  const id = useId();
  return (
    <label className={`toggle${disabled ? ' is-disabled' : ''}`} htmlFor={id}>
      <span className="toggle__text"><span className="toggle__label">{label}</span>{hint ? <span className="toggle__hint">{hint}</span> : null}</span>
      <input id={id} type="checkbox" role="switch" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="toggle__track" aria-hidden="true"><i /></span>
    </label>
  );
}

export function ChipGroup({ label, options, value, onChange }) {
  return (
    <fieldset className="chips">
      <legend className="field__label">{label}</legend>
      <div className="chips__row">
        {options.map(([k, text]) => (
          <label key={k} className={`chip${value === k ? ' is-on' : ''}`}>
            <input type="radio" name={label} value={k} checked={value === k} onChange={() => onChange(k)} />
            {text}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function Field({ label, hint, error, children, id }) {
  return (
    <div className={`field${error ? ' has-error' : ''}`}>
      <label className="field__label" htmlFor={id}>{label}</label>
      {children}
      {hint && !error ? <p className="field__hint">{hint}</p> : null}
      {error ? <p className="field__error" id={`${id}-err`}>{error}</p> : null}
    </div>
  );
}

export function Card({ as: Tag = 'section', className = '', children, ...rest }) {
  return <Tag className={`card ${className}`} {...rest}>{children}</Tag>;
}

export function Badge({ tone = 'plain', children }) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}

export function Empty({ icon = 'spark', title, children, action }) {
  return (
    <div className="empty">
      <span className="empty__icon"><Icon name={icon} size={20} /></span>
      <h3>{title}</h3>
      {children ? <p>{children}</p> : null}
      {action}
    </div>
  );
}

export function ErrorNote({ error, onRetry }) {
  if (!error) return null;
  const offline = error.status === undefined || error.status >= 500;
  return (
    <div className="note note--error" role="alert">
      <Icon name="alert" />
      <p>{offline ? 'The server did not answer. Check that the backend is running, or use the demo.' : error.message}</p>
      {onRetry ? <Button variant="quiet" size="sm" icon="refresh" onClick={onRetry}>Try again</Button> : null}
    </div>
  );
}

export function Skeleton({ rows = 3, height = 64 }) {
  return <div className="skeleton" aria-hidden="true">{Array.from({ length: rows }, (_, i) => <i key={i} style={{ height }} />)}</div>;
}

export function PageHead({ title, sub, children }) {
  return (
    <header className="page-head">
      <div><h1>{title}</h1>{sub ? <p>{sub}</p> : null}</div>
      {children ? <div className="page-head__actions">{children}</div> : null}
    </header>
  );
}

export function Segmented({ value, onChange, options, label }) {
  return (
    <div className="segmented" role="tablist" aria-label={label}>
      {options.map(([k, text, count]) => (
        <button key={k} type="button" role="tab" aria-selected={value === k} className={value === k ? 'is-on' : ''} onClick={() => onChange(k)}>
          {text}{count !== undefined ? <em>{count}</em> : null}
        </button>
      ))}
    </div>
  );
}

/** Ask once more before something that cannot be undone, in place (no modal). */
export function Confirm({ children, confirmLabel, onConfirm, busyLabel }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const ref = useRef(null);
  useEffect(() => { if (asking) ref.current?.focus(); }, [asking]);
  if (!asking) return children(() => setAsking(true));
  return (
    <span className="confirm">
      <Button variant="danger" size="sm" busy={busy} ref={ref} onClick={async () => { setBusy(true); try { await onConfirm(); } finally { setBusy(false); setAsking(false); } }}>
        {busy ? busyLabel || confirmLabel : confirmLabel}
      </Button>
      <Button variant="quiet" size="sm" onClick={() => setAsking(false)}>Keep it</Button>
    </span>
  );
}

// --- toasts -------------------------------------------------------------------------------------------------------
const ToastCtx = createContext(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const push = useCallback((text, tone = 'ok') => {
    const id = Math.random().toString(36).slice(2);
    setItems((xs) => [...xs, { id, text, tone }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 4200);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast toast--${t.tone}`}><Icon name={t.tone === 'error' ? 'alert' : 'check'} />{t.text}</div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
