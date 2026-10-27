"""
Captcha solving.

The portal uses PHP Securimage: 5-6 lowercase alphanumeric characters with
noise lines. Options considered:

* Tesseract: needs a system binary (painful on Windows and on PaaS hosts) and
  is noticeably worse on distorted captcha text.
* A paid captcha-solving API: ruled out by the "no external APIs" spirit of
  the assignment, and it costs money.
* **ddddocr** (chosen): a small ONNX model trained on exactly this kind of
  captcha. It is pip-installable with no system dependencies and runs in
  ~20 ms on CPU. In testing it solved most Securimage captchas on the first or
  second try.

OCR is never 100%, so the service layer wraps it in a retry loop and falls
back to asking the human (manual mode) instead of failing outright.
"""

from __future__ import annotations

import logging
import re
import threading

log = logging.getLogger(__name__)

_ocr = None
_ocr_lock = threading.Lock()


def _get_ocr():
    """Load the ONNX model lazily, once per process.

    Lazy loading keeps app startup fast (Render health checks) and keeps the
    model out of memory if it is never used. The lock prevents two first
    requests from loading it twice.
    """
    global _ocr
    if _ocr is None:
        with _ocr_lock:
            if _ocr is None:
                import ddddocr  # heavy import, deferred on purpose

                _ocr = ddddocr.DdddOcr(show_ad=False)
    return _ocr


def normalise(answer: str) -> str:
    """Clean an OCR or user answer the same way the portal's own input filter does
    (searchByCNR.js strips everything except [a-zA-Z0-9])."""
    return re.sub(r"[^a-zA-Z0-9]", "", answer or "")


def solve(image: bytes) -> str | None:
    """Return the OCR guess, or None if it is obviously wrong.

    Rejecting implausible lengths locally saves a slow portal round trip
    (and burns one less app_token).
    """
    try:
        guess = normalise(_get_ocr().classification(image))
    except Exception as exc:  # a corrupt image or model error must not crash the search
        log.warning("OCR failed: %s", exc)
        return None
    if not 4 <= len(guess) <= 8:
        return None
    return guess.lower()
