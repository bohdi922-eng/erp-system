"""Application-level exceptions."""
from __future__ import annotations


class BusinessError(Exception):
    """Raised for any business-rule violation. `status_code` maps directly
    onto the HTTP response FastAPI should return (a route-level exception
    handler should catch this and translate it — not included in this
    scaffold since no FastAPI app/routes exist yet)."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
