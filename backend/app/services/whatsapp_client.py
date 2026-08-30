"""Minimal WhatsApp Cloud API client (stdlib only — no extra dependency
for a handful of HTTP calls).

Without WHATSAPP_TOKEN / WHATSAPP_PHONE_ID set (see app/config.py), every
call is "simulated": nothing is actually sent over the network, but the
call succeeds and returns a clear marker so the rest of the bot logic
(notifications, inquiry replies) can be built and tested right now,
before a real Meta WhatsApp Business API account exists. Once you have
one, set those two environment variables and nothing else needs to
change — nothing here is real Anthropic/Meta credentials or endpoints
guessed at random, it's the documented Cloud API request shape.
"""
from __future__ import annotations

import json
import urllib.request

from app.config import get_settings

settings = get_settings()

GRAPH_API_VERSION = "v19.0"


class WhatsAppClient:
    def __init__(self) -> None:
        self.token = settings.whatsapp_token
        self.phone_id = settings.whatsapp_phone_id
        self.configured = bool(self.token and self.phone_id)

    def send_text(self, to_phone: str, body: str) -> dict:
        if not self.configured:
            return {"simulated": True, "to": to_phone, "body": body}

        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{self.phone_id}/messages"
        payload = json.dumps({
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": body},
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())

    def fetch_media_bytes(self, media_id: str) -> bytes:
        """Two-step download per Meta's API: resolve the media_id to a
        temporary URL, then fetch the bytes from that URL. Only works with
        real credentials — there's no meaningful "simulated" version of
        downloading a real image."""
        if not self.configured:
            raise RuntimeError("WhatsApp isn't configured — can't fetch real media")

        meta_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{media_id}"
        req = urllib.request.Request(meta_url, headers={"Authorization": f"Bearer {self.token}"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            meta = json.loads(resp.read())

        media_url = meta["url"]
        req2 = urllib.request.Request(media_url, headers={"Authorization": f"Bearer {self.token}"})
        with urllib.request.urlopen(req2, timeout=30) as resp2:
            return resp2.read()
