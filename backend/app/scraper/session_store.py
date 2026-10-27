"""
In-memory parking lot for searches waiting on a human-typed captcha.

Why this needs server state: a captcha answer is only valid for the PHP
session that rendered the image. When OCR gives up, we show the user the
image from session X, so their answer must be submitted through session X.
We keep the live EcourtsClient (cookies + current app_token) here, keyed by a
random search_id.

Trade-offs:
* A process-local dict means the API must run as ONE worker. This is fine for
  an assignment-scale deployment, and the README says so; Redis-pickled
  sessions would be the scale-out path.
* TTL plus a size cap bound memory, so abandoned captchas don't pile up.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from .. import config
from .client import EcourtsClient


@dataclass
class Parked:
    client: EcourtsClient
    action: str  # "cnr" | "case_number"
    params: dict[str, Any]
    expires_at: float = field(default_factory=lambda: time.time() + config.CAPTCHA_SESSION_TTL)


_store: dict[str, Parked] = {}
_lock = threading.Lock()


def _evict_locked() -> None:
    now = time.time()
    for k in [k for k, v in _store.items() if v.expires_at < now]:
        del _store[k]
    # Over capacity: drop the soonest-to-expire (i.e. oldest) entries first.
    while len(_store) > config.MAX_PARKED_SESSIONS:
        oldest = min(_store, key=lambda k: _store[k].expires_at)
        del _store[oldest]


def park(client: EcourtsClient, action: str, params: dict[str, Any], search_id: str | None = None) -> str:
    sid = search_id or secrets.token_urlsafe(16)
    with _lock:
        _evict_locked()
        _store[sid] = Parked(client, action, params)
    return sid


def take(search_id: str) -> Parked | None:
    """Remove and return the entry. Removing (not just reading) means two
    concurrent submissions can't use the same session/token at once."""
    with _lock:
        _evict_locked()
        return _store.pop(search_id, None)
