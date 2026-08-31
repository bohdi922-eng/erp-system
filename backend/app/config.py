"""Application settings. Kept as a plain class + cached factory instead of
pydantic-settings to avoid adding a dependency this scaffold doesn't need
yet — swap in pydantic-settings later if env-var driven config grows."""
from __future__ import annotations

import os
from functools import lru_cache


class Settings:
    app_name: str = "ERP System"
    database_url: str = "sqlite:///./erp_system.db"

    # Document number prefixes
    invoice_prefix: str = "INV"
    quote_prefix: str = "QOT"
    payment_prefix: str = "REC"
    return_prefix: str = "CN"
    repair_prefix: str = "REP"
    purchase_prefix: str = "PO"

    # Business rules
    default_tax_rate: float = 0.14  # 14% Egyptian VAT

    # WhatsApp (Meta Cloud API) — all None until a real account exists.
    # Set these as environment variables when you have them; nothing here
    # is ever hardcoded. Until they're set, whatsapp_client.py runs in
    # "simulated" mode: messages are logged to the DB instead of actually
    # sent, so the rest of the bot logic can be built and tested now.
    whatsapp_token: str | None = os.getenv("WHATSAPP_TOKEN")
    whatsapp_phone_id: str | None = os.getenv("WHATSAPP_PHONE_ID")
    whatsapp_verify_token: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "erp-system-verify")


@lru_cache
def get_settings() -> Settings:
    return Settings()
