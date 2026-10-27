"""
Runtime settings, read from environment variables so one build runs locally
and on Render/Railway without code changes. Plain os.environ is enough for
this many settings; pydantic-settings would be one more dependency for no gain.
"""

import os
import secrets


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# How many OCR guesses to try before asking the human. Each failed guess costs one
# portal round trip (~0.5-2 s). In testing ddddocr usually lands within 1-3 tries
# but sometimes misses 5 in a row, so 8 keeps the manual fallback rare while
# bounding the worst case at ~15 s.
OCR_ATTEMPTS = _int("OCR_ATTEMPTS", 8)

# How long a search waiting for a manual captcha stays resumable. The portal's own
# PHP session times out after roughly 15-20 min idle, so staying under that
# avoids handing back a session the portal has already killed.
CAPTCHA_SESSION_TTL = _int("CAPTCHA_SESSION_TTL", 600)
MAX_PARKED_SESSIONS = _int("MAX_PARKED_SESSIONS", 200)

# Dropdown data (districts, complexes, case types) almost never changes.
META_CACHE_TTL = _int("META_CACHE_TTL", 6 * 3600)

# Signs the opaque refs we hand to the browser (PDF / hearing links), so the
# API can't be used as an open relay for arbitrary portal calls. A random
# per-process default is fine: the worst case after a restart is that old
# links stop working and the user searches again.
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

# Optional outbound proxy for hosts outside India (see README "Hosting & geo-blocking").
ECOURTS_PROXY = os.environ.get("ECOURTS_PROXY") or None

CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
