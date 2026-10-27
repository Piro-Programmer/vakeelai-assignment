"""
Signed, stateless references for follow-up portal calls.

Problem: order PDFs and per-hearing "business" pages are fetched through
portal POSTs whose (encrypted) arguments we scrape from onclick handlers. The
frontend needs a plain URL it can open later.

Option A: keep the portal session alive server-side and look links up by id.
That ties links to RAM: they break on restart or with multiple workers, and
leak memory.
Option B (chosen): pack the arguments into the URL itself. Testing showed
`home/display_pdf` and `home/viewBusiness` work on a FRESH session with no
captcha, so a link only needs the arguments, not the original session.

The packed payload is HMAC-signed so the endpoint can't be abused as an open
relay that forwards arbitrary parameters to the portal.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

from .. import config
from .errors import InvalidInput


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sig(raw: bytes) -> str:
    # 16 bytes of HMAC-SHA256 is ample for an anti-tamper tag and keeps URLs short.
    return _b64(hmac.new(config.SECRET_KEY.encode(), raw, hashlib.sha256).digest()[:16])


def encode(kind: str, payload: dict[str, Any]) -> str:
    raw = json.dumps({"k": kind, "p": payload}, separators=(",", ":")).encode()
    return f"{_b64(raw)}.{_sig(raw)}"


def decode(token: str, kind: str) -> dict[str, Any]:
    try:
        body, sig = token.split(".", 1)
        raw = _unb64(body)
    except Exception as exc:
        raise InvalidInput("Malformed link reference") from exc
    if not hmac.compare_digest(sig, _sig(raw)):
        raise InvalidInput("Link reference is invalid or expired (server restarted?) - please search again")
    data = json.loads(raw)
    if data.get("k") != kind:
        raise InvalidInput("Link reference is of the wrong type")
    return data["p"]
