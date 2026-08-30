"""FastAPI app entrypoint.

Run with:  uvicorn app.main:app --port 8000

This now serves the frontend pages itself (mounted as static files) so the
whole app is one process on one port — no more opening HTML files
separately via file://, and (once `python -m scripts.vendor_assets` has
been run once) no internet connection needed to load styling or fonts.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.exceptions import BusinessError
from app.database import init_db
from app.models import AuthSession
from app.routes import (
    auth, backup, customers, dashboard, inventory, repairs, sales, settings,
    whatsapp,
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

app = FastAPI(title="ERP System API")

# Kept wide-open for local development flexibility even though the
# frontend is now same-origin (served by this same app). Tighten this
# (specific origins) before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(BusinessError)
def business_error_handler(request: Request, exc: BusinessError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.middleware("http")
async def protect_api(request: Request, call_next):
    """Require a valid Bearer session token for every /api route except the
    auth router and /api/health (which the frontend probes at login)."""
    path = request.url.path
    if path.startswith("/api/") and not path.startswith("/api/auth/"):
        token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if token:
            from datetime import datetime
            from app.database import SessionLocal
            from app.models import User
            db = SessionLocal()
            try:
                row = db.query(AuthSession).filter(AuthSession.token == token).first()
                if row is not None and row.expires_at > datetime.now():
                    user = db.get(User, row.user_id)
                    if user is not None and user.is_active:
                        return await call_next(request)
            finally:
                db.close()
        return JSONResponse(status_code=401, content={"detail": "غير مسجل الدخول"})
    return await call_next(request)


@app.on_event("startup")
def on_startup():
    init_db()
    _ensure_demo_passwords()


def _ensure_demo_passwords():
    """Existing databases (seeded before auth existed) have users with no
    password_hash, which would make login impossible. Give any such user the
    demo password so existing installs keep working; fresh installs get
    proper hashes from seed_data.py and are untouched here."""
    from app.database import SessionLocal
    from app.core.security import hash_password
    from app.models import User
    db = SessionLocal()
    try:
        rows = db.query(User).filter(User.password_hash.is_(None)).all()
        if rows:
            demo = hash_password("1234")
            for u in rows:
                u.password_hash = demo
            db.commit()
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(repairs.router, prefix="/api/repairs", tags=["repairs"])
app.include_router(sales.router, prefix="/api/sales", tags=["sales"])
app.include_router(customers.router, prefix="/api/customers", tags=["customers"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(whatsapp.router, prefix="/api/whatsapp", tags=["whatsapp"])
app.include_router(backup.router, prefix="/api/backup", tags=["backup"])


@app.get("/")
def root():
    return RedirectResponse(url="/pages/dashboard.html")


# Vendored offline assets (Tailwind's browser build + local font files) —
# see scripts/vendor_assets.py. Mounted even if the folder is still empty
# (first run before vendoring) so the app doesn't fail to start.
(FRONTEND_DIR / "vendor").mkdir(parents=True, exist_ok=True)
app.mount("/vendor", StaticFiles(directory=str(FRONTEND_DIR / "vendor")), name="vendor")

# Shared frontend JS (auth.js etc.)
(FRONTEND_DIR / "js").mkdir(parents=True, exist_ok=True)
app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")

# The actual pages. html=True lets /pages/dashboard.html (and a bare
# /pages/ later, if an index.html is added) resolve correctly.
app.mount("/pages", StaticFiles(directory=str(FRONTEND_DIR / "pages"), html=True), name="pages")
