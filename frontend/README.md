# Frontend

React 19 + Vite. Two pages:

| URL | File | What it is |
| --- | --- | --- |
| `/` | `index.html` | The landing page: static HTML on the design kit in `public/assets` (fonts, grid, motion, UI fragments) |
| `/app/` | `app/index.html` → `src/` | The app: students book and wait, counsellors run their day, the wellbeing team posts workshops |

The app uses hash routes (`/app/#/book`, `/app/#/sessions`, ...), so FastAPI's `StaticFiles` mount in
`backend/app/main.py` serves it from `frontend/dist` with no catch-all route.

## Run it

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 and http://localhost:5173/app/
```

Vite proxies `/api` to `http://127.0.0.1:8000`, so start the backend too (`uvicorn app.main:app --reload` from
`backend/`). Without it, use a demo account on the sign-in screen.

```bash
npm run build        # dist/, which FastAPI serves at / when it exists
```

## Demo mode

The sign-in screen offers three demo accounts (student, counsellor, wellbeing team). They run
`src/api/demo.js`, an in-browser copy of the backend with the same call names and response shapes and the
same rules (45-minute sessions, 60 for a first visit, quarter-hour starts, waitlist offers held 30 minutes,
events that fill and then queue). State lives in `sessionStorage`; "Reset" in the sidebar starts it over.

## Where things are

```
src/
  api/live.js       every backend route the app calls (bookings, waitlist, events, notify, auth)
  api/demo.js       the demo backend
  api/time.js       UTC from the API, shown in Dubai time (UTC+4), as backend/app/clock.py does
  session.jsx       who is signed in, and in which mode
  components/       Shell (sidebar, phone tab bar), ui.jsx (buttons, toggles, chips, toasts), Icon
  pages/            student/ (Book, Sessions, Waitlist), counsellor/ (Today, Hours), admin/, Workshops, Inbox
  styles/app.css    the app's styles, on the landing page's palette and type
```

## Waiting on the backend

- **Auth.** `routers/auth.py` and `deps.get_current_user` are still TODOs. `src/api/live.js` calls
  `POST /api/auth/login {email, password}`, `POST /api/auth/register`, `POST /api/auth/logout` and
  `GET /api/me` (expected to return `{account_id, role, pseudonym?, display_name?}`). Change the bodies there
  if the backend settles on something else. Until then, sign-in shows a note and points to the demo.
- **Shared names.** `SessionOut.identity` is shown on the counsellor's day when it is filled in.
- **Resources and recommendations** (`routers/recommend.py`) and **analytics** have no screens yet.
