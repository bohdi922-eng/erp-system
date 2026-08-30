"""Database backup download.

GET /api/backup/download streams a consistent snapshot of the SQLite file
using sqlite3's online backup API (safe even while the app holds live
connections). The snapshot is written to a temp file, streamed back as an
attachment named erp_backup_<timestamp>.db, then deleted in the background.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.config import get_settings
from app.core.exceptions import BusinessError

router = APIRouter()


def _database_path() -> Path | None:
    url = get_settings().database_url
    if not url.startswith("sqlite:///"):
        return None
    path = Path(url[len("sqlite:///"):])
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


@router.get("/download")
def download_backup() -> FileResponse:
    src = _database_path()
    if src is None or not src.exists():
        raise BusinessError(f"database file not found at {src}", 404)

    fd, tmp_name = tempfile.mkstemp(prefix="erp_backup_", suffix=".db")
    os.close(fd)
    Path(tmp_name).unlink()  # let sqlite3.connect create it fresh

    with sqlite3.connect(str(src)) as source, sqlite3.connect(tmp_name) as target:
        source.backup(target)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return FileResponse(
        tmp_name,
        media_type="application/octet-stream",
        filename=f"erp_backup_{stamp}.db",
        background=BackgroundTask(_remove_tmp, tmp_name),
    )


def _remove_tmp(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass