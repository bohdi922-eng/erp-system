# ERP System

## Setup (Windows) — one file, does everything

Double-click **`setup.bat`** (in the project root, next to this folder).

First run (needs internet **once**, only for this run):
1. Creates a Python virtual environment
2. Installs dependencies
3. Downloads Tailwind's browser build + the Cairo/Material Symbols fonts
   locally (`frontend/vendor/`) — after this, the app never needs internet
   again, even to look right
4. Creates the database with sample data matching the design mockups
5. Starts the app and opens it in your browser automatically at
   `http://127.0.0.1:8000`

Every run after that: `setup.bat` skips steps 1–4 (already done) and just
starts the app — same as a normal "run" script from then on. A second
window titled **"ERP System Server"** opens and stays open while the app
runs; closing it stops the app.

If you'd rather run things by hand instead of `setup.bat`, see the manual
commands below — everything the batch file does is just these steps in
order.

## Setup (manual / Mac / Linux)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m scripts.vendor_assets   # once, needs internet — makes it offline-capable after
python -m scripts.seed_data       # once, creates erp_system.db with sample data
uvicorn app.main:app --port 8000
```
Then open `http://127.0.0.1:8000` — the app (frontend + API) is served
from this one address now; there's no more need to open the `.html` files
directly.

## Fully offline after first run

Everything the pages load — Tailwind's CSS engine, the Cairo font, the
Material Symbols icon font — is fetched once by `vendor_assets.py` into
`frontend/vendor/` and served locally by the FastAPI app itself
(`/vendor/...`). No CDN, no Google Fonts, no external requests after that
first run. If you ever delete `frontend/vendor/`, just re-run
`vendor_assets.py` (or `setup.bat`) once with internet to regenerate it.

## Database schema: two paths (pick one)

**Quick start (what you've been using so far):** `python -m scripts.seed_data`
calls `init_db()`, which does a plain SQLAlchemy `create_all()` — fine for
a fresh DB, but it will NOT apply changes to an existing `erp_system.db`
if the models change later (it only creates tables that don't exist yet).

**Real migrations (recommended once you start changing the schema):**
```bash
alembic upgrade head
```
This runs `migrations/versions/0001_initial.py`, which creates the exact
same schema as `init_db()` but through a proper, versioned migration you
can upgrade/downgrade and extend with new revisions as the schema grows.
If you already have an `erp_system.db` created via `init_db()`, delete it
first (or start from a fresh file) before switching to Alembic, since
Alembic doesn't know that DB's tables were already created outside of it.

To add a new migration by hand later: create a new file in
`migrations/versions/`, set `down_revision = "0001_initial"` (or whatever
the latest revision is), and write the `upgrade()`/`downgrade()` steps.

## Seed script details

`python -m scripts.seed_data` populates `erp_system.db` with data matching
the design mockups — same customer, products, invoice totals, and
repair-board entries you saw in the original design concepts. It only
needs to run once (skips itself in `setup.bat` if the DB already exists).
Expected output ends with:
```
Seed complete.
  Users: 3
  Products: 7
  Customers: [...]
  Repair center: مركز الصيانة الخارجي المعتمد
```

## What exists so far

```
erp-system/
  setup.bat                 # double-click this — does everything, every time
  backend/
    app/
      main.py                # FastAPI app — serves the API AND the frontend pages
      config.py               # Settings (app name, DB URL, doc-number prefixes, VAT rate)
      database.py              # engine/session + init_db()
      core/
        enums.py               # DocType, ItemStatus, InvoiceStatus, RepairStatus, ...
        exceptions.py            # BusinessError
        numbering.py             # next_number() — sequential INV-0001 style numbers
      models/__init__.py         # All tables
      routes/
        dashboard.py              # live KPI summary
        repairs.py                 # board view + full state-machine actions
        sales.py                    # item lookup, invoice create/list
        customers.py                 # list, statement, aging report
        inventory.py                  # items/products list
        settings.py                    # shop info get/update, users list
      services/
        crm_service.py                 # customers, balances, statements, aging (fixed)
        sales_service.py                # invoices, payments, returns (fixed)
        inventory_service.py             # items, stock movements, purchase receiving (fixed)
        repairs_service.py                # repair hub state machine (fixed)
    migrations/                          # Alembic — see the schema section above
    scripts/
      vendor_assets.py                    # one-time: downloads Tailwind/fonts for offline use
      seed_data.py                         # populates the DB with mockup-matching data
    requirements.txt

  frontend/
    vendor/                # created by vendor_assets.py — tailwind.js, fonts.css, fonts/
    pages/
      dashboard.html         # all 6 pages: live data, dynamic POS cart, working
      repairs_board.html      # repair-board actions with a real modal (not prompt())
      customer_statement.html
      inventory.html
      sales_new_invoice.html
      settings.html
```

## Not built yet

- Auth (the real project's spec calls for USB-dongle auth — flagged
  earlier as needing its own design pass, not started)
- WhatsApp bot / AI assistant integrations (separate large features,
  not started — need their own design pass before any code)
- Settings page: only shop info + user list are wired; no create/edit
  user flow yet
- POS: barcode/serial add-to-cart + live name search both work, but
  there's still no full product browsing/catalog view
