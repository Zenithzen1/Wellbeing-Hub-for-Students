// One stroke icon set for the app (16px grid, 1.6 stroke), drawn to match the landing page's UI glyphs.
const PATHS = {
  calendar: <><path d="M2.5 4h11v9.5h-11z" /><path d="M2.5 7h11M5.5 2.5v3M10.5 2.5v3" /></>,
  list: <><path d="M5.5 4h8M5.5 8h8M5.5 12h8" /><circle cx="2.6" cy="4" r=".6" /><circle cx="2.6" cy="8" r=".6" /><circle cx="2.6" cy="12" r=".6" /></>,
  clock: <><circle cx="8" cy="8" r="5.5" /><path d="M8 5v3l2 1.5" /></>,
  users: <><circle cx="6" cy="6" r="2.3" /><path d="M2 13c.5-2 2-3 4-3s3.5 1 4 3" /><path d="M10.5 3.9a2.2 2.2 0 0 1 0 4.2M12 10.2c1 .5 1.7 1.4 2 2.8" /></>,
  bell: <><path d="M4 11V7a4 4 0 0 1 8 0v4l1 1.5H3z" /><path d="M6.5 14a1.6 1.6 0 0 0 3 0" /></>,
  spark: <><path d="M8 2.5v3M8 10.5v3M2.5 8h3M10.5 8h3M4.2 4.2l1.9 1.9M9.9 9.9l1.9 1.9M11.8 4.2 9.9 6.1M6.1 9.9l-1.9 1.9" /></>,
  out: <><path d="M9.5 3.5h3v9h-3" /><path d="M7 5.5 4.5 8 7 10.5M4.5 8h6" /></>,
  plus: <path d="M8 3v10M3 8h10" />,
  x: <path d="m4 4 8 8M12 4l-8 8" />,
  check: <path d="m3.5 8.4 2.8 2.8 6.2-6.4" />,
  left: <path d="M10 4 6 8l4 4" />,
  right: <path d="m6 4 4 4-4 4" />,
  menu: <path d="M2.5 5h11M2.5 11h11" />,
  lock: <><rect x="3.5" y="7" width="9" height="6.5" rx="1.5" /><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" /></>,
  tag: <><path d="M2.5 2.5h5.2l5.8 5.8-5.2 5.2-5.8-5.8z" /><circle cx="5.5" cy="5.5" r=".9" /></>,
  inbox: <><path d="M2.5 9h3l1 1.5h3l1-1.5h3" /><path d="M2.5 9 4 3.5h8L13.5 9v3.5h-11z" /></>,
  send: <><path d="m2.5 7.5 11-5-4 11-2-4.5z" /><path d="m7.5 9 6-6.5" /></>,
  alert: <><path d="M8 2.5 14 13H2z" /><path d="M8 6.5v3M8 11.3v.2" /></>,
  trash: <><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 9h5.8l.6-9" /></>,
  arrow: <path d="M3 8h9.5M9 4.5 12.5 8 9 11.5" />,
  hours: <><path d="M2.5 4h11v9.5h-11z" /><path d="M2.5 7h11M5.5 2.5v3M10.5 2.5v3M6 10.2l1.4 1.3L10 9" /></>,
  block: <><circle cx="8" cy="8" r="5.5" /><path d="M4.2 11.8 11.8 4.2" /></>,
  megaphone: <><path d="M3 6.5v3h2l5 3v-9l-5 3z" /><path d="M12 6.3a2.2 2.2 0 0 1 0 3.4" /></>,
  workshop: <><circle cx="8" cy="4.5" r="2" /><path d="M3 13.5c.6-2.6 2.6-4 5-4s4.4 1.4 5 4" /></>,
  eyeoff: <><path d="M2 8s2.2-4 6-4 6 4 6 4-2.2 4-6 4-6-4-6-4z" /><path d="M3 13 13 3" /></>,
  refresh: <><path d="M12.8 6.5A5 5 0 0 0 3.5 6M3.2 9.5A5 5 0 0 0 12.5 10" /><path d="M3.5 3v3h3M12.5 13v-3h-3" /></>,
};

export function Icon({ name, size = 16, className = '', title }) {
  return (
    <svg className={`icon ${className}`} width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor"
      strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden={title ? undefined : true} role={title ? 'img' : undefined}>
      {title ? <title>{title}</title> : null}
      {PATHS[name]}
    </svg>
  );
}

export function Mark({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className="brand-mark">
      <rect x="2" y="2.5" width="20" height="5.5" rx="2.75" /><rect x="2" y="9.25" width="14" height="5.5" rx="2.75" /><rect x="2" y="16" width="8" height="5.5" rx="2.75" />
    </svg>
  );
}
