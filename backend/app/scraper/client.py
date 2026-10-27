"""
Low-level HTTP client for the eCourts v6 portal.

This module reproduces what the portal's own jQuery code does. The behaviour
below was found by reading the site's JS (components.js, common_header.js,
searchByCNR.js, searchByCaseStatus.js) and watching the Network tab:

1. **Session cookies.** The first GET sets `SERVICES_SESSID` (PHP session) and
   `JSESSION`. Captcha answers, tokens and the selected court all live in that
   PHP session, so a whole search MUST use one `requests.Session`.

2. **app_token (a rotating CSRF token).** Every AJAX POST sends
   `ajax_req=true&app_token=<token>`, and every JSON response returns a NEW
   `app_token` that must be used for the next call. The token is NOT on the
   bare homepage (it renders `value=""` for a fresh session). It IS embedded
   in `?p=casestatus/index`, so we bootstrap from that page.

3. **Rotating anti-bot header.** `ajaxCall()` in `components.js?v=<ts>` sends
   two custom headers, e.g. `{"delimeter": "sjhrt654", "Cgfhfhgrt65": "sjhrt654"}`.
   Both the header NAME and the VALUE change whenever the `v=` version changes,
   and requests without them get "Invalid Request". Hardcoding them would break
   within hours, so we download the exact components.js that the bootstrap page
   references and regex the pair out of the `ajaxCall` function.

4. **Errors come back as HTTP 200**, e.g. `{"errormsg": "Invalid Captcha...", "app_token": ...}`.
   `post()` turns these into typed exceptions (see errors.py).

Trade-off: we use plain `requests`, not a headless browser. It's ~50x lighter
(important on a free 512MB host), faster and deterministic. The cost is that
we must track the token/header rules ourselves. That logic is isolated here,
so a portal change means editing one file.
"""

from __future__ import annotations

import logging
import random
import re
import threading
import time
from typing import Any

import requests

from .errors import CaptchaError, CaseNotFound, PortalUnavailable, SessionExpired

log = logging.getLogger(__name__)

ORIGIN = "https://services.ecourts.gov.in"
BASE = ORIGIN + "/ecourtindia_v6/"

# A normal desktop Chrome UA. The portal doesn't appear to fingerprint the UA,
# but a python-requests UA is an easy thing for a WAF to block.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

_TOKEN_RE = re.compile(r"id=['\"]app_token['\"]\s+value=\"([0-9a-f]*)\"")
_COMPONENTS_RE = re.compile(r'src="(/ecourtindia_v6/js/components\.js\?v=\d+)"')
_DELIM_VALUE_RE = re.compile(r'var\s+delimeter\s*=\s*"([^"]+)"')
_DELIM_HEADER_RE = re.compile(r'"([\w-]+)"\s*:\s*delimeter')

# The portal is slow (often 5-15s per call), so timeouts are generous.
TIMEOUT = (15, 60)  # (connect, read)


class EcourtsClient:
    """One portal session. Not thread-safe, so each search gets its own instance.

    A per-instance lock still serialises calls. The manual-captcha flow can
    leave a client parked in the session store, and a double-clicked request
    must not use the same app_token twice: the token would desync and the
    session would die.
    """

    def __init__(self, proxy: str | None = None):
        self.http = requests.Session()
        self.http.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        if proxy:
            # Optional escape hatch for hosting outside India (see README: geo risk).
            self.http.proxies = {"http": proxy, "https": proxy}
        self.app_token = ""
        self.landing_html = ""
        self.ajax_headers: dict[str, str] = {}
        self.created_at = time.time()
        self.lock = threading.Lock()

    # ------------------------------------------------------------------ setup
    def bootstrap(self) -> None:
        """Create the PHP session, get the first app_token and the anti-bot headers."""
        try:
            # 1st GET only sets cookies; its token is always empty for a new session.
            self.http.get(BASE, timeout=TIMEOUT)
            page = self.http.get(
                BASE + "?p=casestatus/index", headers={"Referer": BASE}, timeout=TIMEOUT
            )
            page.raise_for_status()
        except requests.RequestException as exc:
            raise PortalUnavailable("Could not reach the eCourts portal", detail=str(exc)) from exc

        html = page.text
        self.landing_html = html  # holds the state <select>, so meta can reuse it
        m = _TOKEN_RE.search(html)
        if not m or not m.group(1):
            raise PortalUnavailable("Portal did not issue a session token (layout changed or IP blocked?)")
        self.app_token = m.group(1)
        self.ajax_headers = self._extract_ajax_headers(html)
        log.info("eCourts session ready (headers=%s)", list(self.ajax_headers))

    def _extract_ajax_headers(self, html: str) -> dict[str, str]:
        m = _COMPONENTS_RE.search(html)
        if not m:
            raise PortalUnavailable("components.js not found on the bootstrap page")
        js = self.http.get(ORIGIN + m.group(1), timeout=TIMEOUT).text
        start = js.find("function ajaxCall(")
        if start < 0:
            raise PortalUnavailable("ajaxCall() not found in components.js")
        # Search only the body of ajaxCall, up to its `error:` handler. Other functions
        # in the file could hold decoy/older pairs.
        body = js[start : js.find("error:", start)]
        value = _DELIM_VALUE_RE.search(body)
        names = _DELIM_HEADER_RE.findall(body)
        if not value or not names:
            raise PortalUnavailable("Could not extract anti-bot headers from components.js")
        return {name: value.group(1) for name in names}

    # ------------------------------------------------------------- transport
    def post(self, endpoint: str, data: dict[str, Any] | None = None, *, retries: int = 2) -> dict:
        """POST to `?p=<endpoint>` the way the site's ajaxCall() does, and rotate the token.

        Retries cover network errors and 5xx only. Application-level errors are
        raised immediately, because retrying a wrong captcha with the same
        answer is pointless.
        """
        payload = dict(data or {})
        payload["ajax_req"] = "true"
        headers = {
            **self.ajax_headers,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": BASE,
            "Origin": ORIGIN,
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            payload["app_token"] = self.app_token
            try:
                resp = self.http.post(BASE + "?p=" + endpoint, data=payload, headers=headers, timeout=TIMEOUT)
                if resp.status_code >= 500:
                    raise PortalUnavailable(f"Portal returned HTTP {resp.status_code}")
                body = resp.json()
                break
            except (requests.RequestException, ValueError, PortalUnavailable) as exc:
                last_exc = exc
                log.warning("POST %s failed (attempt %d): %s", endpoint, attempt + 1, exc)
                time.sleep(1.5 * (attempt + 1))
        else:
            raise PortalUnavailable("eCourts portal is not responding", detail=str(last_exc))

        # Always pick up the new token, even from error responses. The site's JS does
        # the same, and skipping it kills the session on the next call.
        if body.get("app_token"):
            self.app_token = body["app_token"]
        self._raise_for_errormsg(body)
        return body

    @staticmethod
    def _raise_for_errormsg(body: dict) -> None:
        msg = body.get("errormsg")
        if not msg:
            return
        text = re.sub(r"<[^>]+>", " ", str(msg))
        text = re.sub(r"\s+", " ", text).strip()
        low = text.lower()
        if "captcha" in low:
            raise CaptchaError(text)
        if "session" in low or "invalid request" in low:
            raise SessionExpired(text)
        if "not found" in low or "not exist" in low or "no record" in low:
            raise CaseNotFound(text)
        # Anything else is surfaced verbatim. The portal's own wording is usually
        # the most useful thing we can show the user.
        raise PortalUnavailable(text)

    def captcha_image(self) -> bytes:
        """Fetch a fresh captcha PNG. Securimage keeps the answer in the PHP session,
        so the image MUST come from the same session that later submits the answer."""
        url = BASE + "vendor/securimage/securimage_show.php?" + str(random.random())
        try:
            resp = self.http.get(url, headers={"Referer": BASE}, timeout=TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise PortalUnavailable("Could not load captcha", detail=str(exc)) from exc
        return resp.content

    def get_binary(self, path: str) -> requests.Response:
        """GET a portal-relative file (e.g. an order PDF) with this session's cookies."""
        url = path if path.startswith("http") else BASE + path.lstrip("/")
        try:
            resp = self.http.get(url, headers={"Referer": BASE}, timeout=TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise PortalUnavailable("Could not download file", detail=str(exc)) from exc
        return resp
