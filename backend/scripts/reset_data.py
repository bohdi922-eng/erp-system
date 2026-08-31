"""Wipe all program data and start fresh with clean sample data.

Run from backend/: `python -m scripts.reset_data`
Or just double-click reset.bat in the project root — it does this for you.

This is the ONE command to remember for "start over": it deletes the
SQLite database file completely (every sale, repair, customer, message —
everything) and re-creates it with the same sample data
`python -m scripts.seed_data` normally creates on first run.
"""
from __future__ import annotations

from pathlib import Path

from app.config import get_settings


def run() -> None:
    settings = get_settings()
    # database_url looks like "sqlite:///./erp_system.db" — strip the
    # SQLAlchemy prefix to get a plain path, relative to wherever this is
    # run from (same assumption app/database.py already makes).
    db_path = Path(settings.database_url.removeprefix("sqlite:///"))

    if db_path.exists():
        db_path.unlink()
        print(f"Deleted {db_path.resolve()}")
    else:
        print(f"No existing database found at {db_path.resolve()} — nothing to delete.")

    print("Creating fresh sample data...")
    from scripts.seed_data import run as seed_run
    seed_run()


if __name__ == "__main__":
    run()
