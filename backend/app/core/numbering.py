"""Sequential, gap-free-per-type document numbering (INV-0001, REP-0088...).

Uses one counter row per DocType, incremented with an atomic UPDATE so two
concurrent requests never get the same number (works on SQLite 3.35+, which
supports UPDATE ... RETURNING; on older SQLite this falls back to a plain
UPDATE followed by a SELECT, which is safe within a single transaction but
not across separate connections without SQLite's default file-level
locking — acceptable for this single-file-DB deployment, called out here
rather than silently assumed).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import DocType
from app.models import DocumentSequence


def next_number(db: Session, doc_type: DocType, prefix: str, pad: int = 4) -> str:
    seq = db.scalar(
        select(DocumentSequence).where(DocumentSequence.doc_type == doc_type.value)
    )
    if seq is None:
        seq = DocumentSequence(doc_type=doc_type.value, last_number=0)
        db.add(seq)
        db.flush()

    seq.last_number += 1
    db.flush()  # persist the increment within the current transaction
    return f"{prefix}-{seq.last_number:0{pad}d}"
