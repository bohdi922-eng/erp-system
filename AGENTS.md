# ERP System — Agent Guide

FastAPI + SQLAlchemy (SQLite) backend serving an offline-capable HTML
frontend. All pages and the API are served from one FastAPI process
(`uvicorn app.main:app --port 8000`, open http://127.0.0.1:8000).

## Commands

- Run the app: `cd backend && uvicorn app.main:app --port 8000`
  (or double-click `setup.bat` on Windows — creates venv, installs deps,
  seeds DB, starts server)
- First-time assets (tailwind.js + fonts, once, needs internet):
  `python -m scripts.vendor_assets`
- Fresh database with sample data: `python -m scripts.seed_data`
- Schema migrations: `cd backend && alembic upgrade head`

## Layout

- `backend/app/main.py` — FastAPI app (API + static frontend)
- `backend/app/config.py` — settings (DB URL, doc-number prefixes, VAT)
- `backend/app/core/` — enums, BusinessError, sequential numbering
- `backend/app/models/__init__.py` — all SQLAlchemy tables
- `backend/app/routes/` — one router per area (dashboard, sales, repairs,
  customers, inventory, settings)
- `backend/app/services/` — business logic per area
- `backend/migrations/` — Alembic revisions
- `backend/scripts/` — `vendor_assets.py`, `seed_data.py`
- `frontend/pages/*.html` — the UI pages

## Conventions

- Arabic UI text; English identifiers/code.
- Money in EGP, one `decimal(12,2)` total per document.
- Use `BusinessError` (in `app/core/exceptions.py`) for business rule
  violations — never raise HTTP errors from services.
- Document numbers come from `app.core.numbering.next_number()` — do not
  generate them manually.
- Keep services free of FastAPI/Request dependencies (callable from CLI too).

## Rules

- `.gitignore` excludes `*.db`, `.venv/`, `.env` — never commit those.
- No secrets hardcoded — WhatsApp credentials come from env vars
  (`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_VERIFY_TOKEN`).
- Changes to the schema need a new Alembic revision (see `backend/README.md`).
- After any service/route change, verify with a quick manual run that the
  app still starts (there is no test suite yet).