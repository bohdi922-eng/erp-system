"""Password hashing + session tokens.

PBKDF2-HMAC-SHA256 via stdlib (no extra dependency, fully offline) with a
per-user random salt and 200k iterations. Stored format:
    pbkdf2$<iterations>$<salt_b64>$<hash_b64>
Supports verifying legacy plain-sha256 hashes (settings.py placeholder) so
existing rows keep working after the upgrade.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_ITERATIONS = 200_000
_PREFIX = "pbkdf2"


def hash_password(raw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt, _ITERATIONS)
    return "{0}${1}${2}${3}".format(
        _PREFIX,
        _ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(dk).decode("ascii"),
    )


def verify_password(raw: str, stored: str | None) -> bool:
    if not stored or not raw:
        return False
    parts = stored.split("$")
    if len(parts) == 4 and parts[0] == _PREFIX:
        try:
            iterations = int(parts[1])
            salt = base64.b64decode(parts[2])
            expected = base64.b64decode(parts[3])
            dk = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt, iterations)
            return hmac.compare_digest(dk, expected)
        except (ValueError, TypeError):
            return False
    # Legacy: the old settings.py stored raw sha256 hex.
    return hmac.compare_digest(
        hashlib.sha256(raw.encode("utf-8")).hexdigest(), stored
    )


def generate_token() -> str:
    return secrets.token_urlsafe(32)