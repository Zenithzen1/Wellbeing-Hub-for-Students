# Well-Being Hub for Students

ACOL-2010 team project (Aditya, Divyam, Rithwik). FastAPI + SQLite backend with every data structure
written from scratch, React + Vite frontend (not set up yet).

## Layout

```
backend/
  app/
    main.py          FastAPI app; startup = create tables, rebuild DS, start scheduler
    config.py db.py models.py schemas.py auth.py deps.py clock.py scheduler.py
    ds/              pure data structures (DataStructs.py), no imports from the rest of app/
    services/        business rules: identity, booking, waitlist, events, notify, recommend, analytics
    routers/         one file per URL group, mounted under /api
  tests/ ds/ services/ api/
  bench/             timing scripts + plots for the report
  seed.py            fake demo data only
frontend/src/ pages/ components/ api/ hooks/
docs/
```

## Run the backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt
copy ..\.env.example ..\.env     # then fill in the secrets
uvicorn app.main:app --reload    # one worker only; http://localhost:8000/docs
```

Checks before every push: `ruff check .` and `pytest` (from `backend/`).

Import data structures through the package: `from app.ds import HashMap, IntervalTree`.
