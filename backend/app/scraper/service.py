"""
High-level search flows: what the API calls.

Flow overview (see docs/REQUEST_FLOW.md for the raw requests):

CNR search
    bootstrap -> [captcha image -> OCR -> cnr_status/searchByCNR]* -> parse HTML

Case-number search
    bootstrap -> casestatus/set_data (pins the court in the PHP session)
              -> [captcha image -> OCR -> casestatus/submitCaseNo]* -> list of matches
    then, per match the user opens:
    fresh session -> home/viewHistory (no captcha needed) -> parse HTML

[...]* is the captcha loop: up to OCR_ATTEMPTS automatic tries, then the
search is "parked" and the user is shown the captcha (manual fallback). The
user's answer resumes the SAME session through `resume_with_captcha`.
"""

from __future__ import annotations

import base64
import datetime as dt
import logging
import re
import threading
import time
from typing import Any, Callable

from bs4 import BeautifulSoup

from .. import config
from . import captcha, refs, session_store
from .client import EcourtsClient
from .errors import CaptchaError, CaseNotFound, InvalidInput, PortalUnavailable, SessionExpired
from .parser import parse_business, parse_case_history, parse_case_list

log = logging.getLogger(__name__)


# =================================================================== helpers
def _new_client() -> EcourtsClient:
    c = EcourtsClient(proxy=config.ECOURTS_PROXY)
    c.bootstrap()
    return c


def _options(html: str) -> list[dict[str, str]]:
    """<option value=..>label</option> -> [{value, label}], skipping 'Select ...' placeholders."""
    out = []
    for opt in BeautifulSoup(html or "", "lxml").find_all("option"):
        value = (opt.get("value") or "").strip()
        if value in ("", "0"):
            continue
        out.append({"value": value, "label": " ".join(opt.get_text().split())})
    return out


def _split_complex(raw: str) -> tuple[str, list[str], bool]:
    """'1260011@1,2,3,4@Y' -> ('1260011', ['1','2','3','4'], True).

    The portal packs three things into the complex <option> value: the
    complex code, the establishment codes it contains, and a flag. 'Y' means
    "establishments keep separate registers, so the user MUST pick one"
    (searchByCaseStatus.js shows alert #71 otherwise).
    """
    parts = (raw or "").split("@")
    if not parts[0].isdigit():
        raise InvalidInput("Invalid court complex value")
    ests = [e for e in (parts[1].split(",") if len(parts) > 1 else []) if e]
    return parts[0], ests, (len(parts) > 2 and parts[2] == "Y")


def _captcha_payload(client: EcourtsClient, action: str, params: dict, message: str, search_id: str | None = None) -> dict:
    """Park the session and return what the UI needs to show the captcha."""
    image = client.captcha_image()  # MUST come from the parked session
    sid = session_store.park(client, action, params, search_id)
    return {
        "status": "captcha_required",
        "search_id": sid,
        "captcha_image": "data:image/png;base64," + base64.b64encode(image).decode(),
        "message": message,
        "expires_in": config.CAPTCHA_SESSION_TTL,
    }


# ============================================================ result shaping
def _finalise_case(parsed: dict[str, Any], *, court_complex_code: str | None = None) -> dict[str, Any]:
    """Swap the raw onclick args for signed refs and API URLs, and add a summary.

    Doing it here (not in parser.py) keeps the parser pure (HTML in, data out)
    and keeps all knowledge about OUR API's URLs in the service layer.
    """
    for row in parsed.get("hearing_history", []):
        args = row.pop("_business_args", None)
        if args:
            ref = refs.encode("biz", {"a": args, "cx": court_complex_code})
            row["business_url"] = f"/api/cases/business?ref={ref}"
    ctx = parsed.pop("_context", None) or {}
    for key in ("interim_orders", "final_orders"):
        for row in parsed.get(key, []):
            args = row.pop("_pdf_args", None)
            # The PDF ref also carries the case context: display_pdf only works after
            # the same session has opened this case via viewHistory (found by testing:
            # a cold display_pdf returns "Session timeout").
            row["pdf_url"] = (
                f"/api/cases/order-pdf?ref={refs.encode('pdf', {'a': args, 'c': ctx})}" if args else None
            )

    cd, cs = parsed.get("case_details", {}), parsed.get("case_status", {})
    pet = parsed.get("petitioners") or []
    res = parsed.get("respondents") or []
    parsed["summary"] = {
        "cnr": cd.get("cnr_number"),
        "title": f"{pet[0]['name'] if pet else '?'} vs {res[0]['name'] if res else '?'}",
        "case_type": cd.get("case_type"),
        "registration_number": cd.get("registration_number"),
        "court": parsed.get("court_name"),
        # A disposed case has a decision date and no next hearing; a pending one the reverse.
        "is_disposed": bool(cs.get("decision_date")) or "disposed" in (cs.get("status") or "").lower(),
        "next_hearing_date": cs.get("next_hearing_date"),
        "decision_date": cs.get("decision_date"),
        "stage": cs.get("case_stage") or cs.get("status"),
    }
    parsed["source"] = {
        "portal": "https://services.ecourts.gov.in/ecourtindia_v6/",
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    return parsed


# ============================================================ captcha attempts
def _attempt(client: EcourtsClient, action: str, params: dict, code: str) -> dict:
    """One submission with one captcha answer. Raises CaptchaError if wrong."""
    if action == "cnr":
        body = client.post("cnr_status/searchByCNR/", {"cino": params["cnr"], "fcaptcha_code": code})
        html = body.get("casetype_list") or ""
        parsed = parse_case_history(html) if html else {}
        if not parsed.get("case_details"):
            # Unknown CNRs return a short message fragment instead of the case tables.
            msg = " ".join(BeautifulSoup(html, "lxml").get_text(" ").split()) if html else ""
            raise CaseNotFound(msg or f"No case found for CNR {params['cnr']}")
        return {"status": "ok", "type": "case", "case": _finalise_case(parsed)}

    if action == "case_number":
        p = params
        body = client.post(
            "casestatus/submitCaseNo",
            {
                "case_type": p["case_type"],
                "search_case_no": p["case_number"],
                "rgyear": p["year"],
                "case_captcha_code": code,
                "state_code": p["state_code"],
                "dist_code": p["dist_code"],
                "court_complex_code": p["complex_code"],
                "est_code": p["est_code"],
                "case_no": p["case_number"],
            },
        )
        matches = parse_case_list(body.get("case_data") or "")
        if not matches:
            raise CaseNotFound("No case found for the given case type, number and year")
        for m in matches:
            m["detail_ref"] = refs.encode("hist", {"a": m.pop("_history_args")})
        return {"status": "ok", "type": "matches", "matches": matches}

    raise InvalidInput(f"Unknown action {action}")


def _prepare(client: EcourtsClient, action: str, params: dict) -> None:
    """Per-session setup before a captcha submit.

    `set_data` stores the selected complex/establishment in the PHP session,
    the same call the browser makes when you pick an establishment. Skipping
    it gave inconsistent results, so we mirror the browser exactly.
    """
    if action == "case_number":
        client.post(
            "casestatus/set_data",
            {
                "complex_code": params["complex_raw"],
                "selected_state_code": params["state_code"],
                "selected_dist_code": params["dist_code"],
                "selected_est_code": params["est_code"],
            },
        )


def _run_auto(action: str, params: dict) -> dict:
    """Bootstrap a session and try OCR up to OCR_ATTEMPTS times, then fall back to manual."""
    client = _new_client()
    _prepare(client, action, params)
    rebuilt = False
    attempt = 0
    while attempt < config.OCR_ATTEMPTS:
        attempt += 1
        guess = captcha.solve(client.captcha_image())
        if not guess:
            continue  # implausible OCR output, so get a fresh image without wasting a submit
        try:
            result = _attempt(client, action, params, guess)
            result["captcha"] = {"mode": "auto", "attempts": attempt}
            return result
        except CaptchaError:
            log.info("OCR guess %r rejected (attempt %d)", guess, attempt)
        except SessionExpired:
            # The token desynced or the portal dropped the session: rebuild once, keep counting.
            if rebuilt:
                raise
            rebuilt = True
            client = _new_client()
            _prepare(client, action, params)
    return _captcha_payload(client, action, params, "Automatic captcha solving failed. Please type the characters shown.")


# =================================================================== public
_CNR_RE = re.compile(r"^[A-Z0-9]{16}$")


def search_cnr(cnr: str) -> dict:
    # Normalise the way people actually paste CNRs: spaces, dashes, lowercase.
    cnr = re.sub(r"[\s\-]", "", cnr or "").upper()
    if not _CNR_RE.match(cnr):
        raise InvalidInput("CNR must be exactly 16 letters/digits, e.g. DLND020000602007")
    return _run_auto("cnr", {"cnr": cnr})


def search_case_number(state_code: str, dist_code: str, court_complex: str, est_code: str | None,
                       case_type: str, case_number: str, year: str) -> dict:
    complex_code, ests, needs_est = _split_complex(court_complex)
    est_code = (est_code or "").strip()
    if needs_est and not est_code:
        raise InvalidInput("This court complex requires selecting an establishment")
    if est_code and ests and est_code not in ests:
        raise InvalidInput("Establishment does not belong to the selected court complex")
    case_number = (case_number or "").strip().lstrip("0") or "0"
    if not case_number.isdigit() or len(case_number) > 7:
        raise InvalidInput("Case number must be numeric (up to 7 digits)")
    year = (year or "").strip()
    if not (year.isdigit() and 1900 <= int(year) <= dt.date.today().year):
        raise InvalidInput("Year must be a 4-digit year not in the future")
    if not (state_code.isdigit() and dist_code.isdigit() and case_type):
        raise InvalidInput("State, district and case type are required")
    params = {
        "state_code": state_code, "dist_code": dist_code, "complex_raw": court_complex,
        "complex_code": complex_code, "est_code": est_code if needs_est else "",
        "case_type": case_type, "case_number": case_number, "year": year,
    }
    return _run_auto("case_number", params)


def resume_with_captcha(search_id: str, code: str) -> dict:
    """Manual fallback: submit the human's answer on the parked session."""
    parked = session_store.take(search_id)
    if parked is None:
        raise SessionExpired("This captcha has expired. Please start the search again.")
    code = captcha.normalise(code)
    if not code:
        return _captcha_payload(parked.client, parked.action, parked.params, "Please enter the captcha.", search_id)
    with parked.client.lock:
        try:
            result = _attempt(parked.client, parked.action, parked.params, code)
        except CaptchaError:
            return _captcha_payload(parked.client, parked.action, parked.params,
                                    "Incorrect captcha, please try again.", search_id)
    result["captcha"] = {"mode": "manual"}
    return result


def case_detail(detail_ref: str) -> dict:
    """Open a case from the case-number result list (viewHistory, no captcha needed)."""
    a = refs.decode(detail_ref, "hist")["a"]
    if len(a) < 9:
        raise InvalidInput("Malformed case reference")
    # Mirrors components.js viewHistory(case_no, cino, court_code, hideparty,
    # search_flag, state_code, dist_code, complex_code, search_by).
    client = _new_client()
    body = client.post(
        "home/viewHistory",
        {
            "court_code": a[2], "state_code": a[5], "dist_code": a[6], "court_complex_code": a[7],
            "case_no": a[0], "cino": a[1], "hideparty": a[3], "search_flag": a[4], "search_by": a[8],
        },
    )
    html = body.get("data_list") or ""
    parsed = parse_case_history(html)
    if not parsed.get("case_details"):
        raise CaseNotFound("The portal returned no details for this case")
    return {"status": "ok", "type": "case", "case": _finalise_case(parsed, court_complex_code=a[7])}


def hearing_business(ref: str) -> dict:
    """Daily-status ("business") page for one hearing date."""
    p = refs.decode(ref, "biz")
    a = p["a"]
    if len(a) < 11:
        raise InvalidInput("Malformed hearing reference")
    # Mirrors viewBusiness(court_code, dist_code, n_dt, case_number, state_code,
    # businessStatus, todays_date1, court_no, national_court_code, search_by, srno).
    data = {
        "court_code": a[0], "state_code": a[4], "dist_code": a[1], "nextdate1": a[2], "case_number1": a[3],
        "disposal_flag": a[5], "businessDate": a[6], "court_no": a[7], "national_court_code": a[8],
        "search_by": a[9], "srno": a[10],
    }
    if a[9] != "cnr" and p.get("cx"):
        data["court_complex_code"] = p["cx"]
    body = _new_client().post("home/viewBusiness", data)
    return {"status": "ok", "business": parse_business(body.get("data_list") or "")}


def order_pdf(ref: str) -> tuple[bytes, str]:
    """Download an order/judgment PDF via display_pdf, which returns a temp path."""
    p = refs.decode(ref, "pdf")
    a, ctx = p["a"], p.get("c") or {}
    if len(a) < 5:
        raise InvalidInput("Malformed order reference")
    client = _new_client()
    if ctx.get("cino"):
        # Warm-up: make this case the session's "current" case. viewHistory needs
        # no captcha and works with just cino + court coordinates.
        client.post("home/viewHistory", {
            "court_code": ctx.get("court_code", ""), "state_code": ctx.get("state_code", ""),
            "dist_code": ctx.get("dist_code", ""), "court_complex_code": ctx.get("court_complex_code", ""),
            "case_no": "", "cino": ctx["cino"], "hideparty": "",
            "search_flag": "CScaseNumber", "search_by": "CScaseNumber",
        })
    body = client.post(
        "home/display_pdf",
        {"normal_v": a[0], "case_val": a[1], "court_code": a[2], "filename": a[3], "appFlag": a[4]},
    )
    path = body.get("order")
    if not path:
        raise CaseNotFound("Order document is not available on the portal")
    resp = client.get_binary(path)
    if not resp.content.startswith(b"%PDF"):
        raise PortalUnavailable("Portal did not return a PDF for this order")
    return resp.content, path.rsplit("/", 1)[-1]


# ======================================================== dropdown metadata
class _MetaService:
    """Cascading dropdown data with one shared session and a TTL cache.

    Dropdown lookups need no captcha, so a single long-lived session serves
    them all. That's far cheaper than bootstrapping (3 requests) for every
    dropdown change. A lock serialises its use because the app_token is a
    strictly sequential chain. On any session error we rebuild it once.
    """

    def __init__(self):
        self._client: EcourtsClient | None = None
        self._lock = threading.Lock()
        self._cache: dict[tuple, tuple[float, Any]] = {}

    def _call(self, key: tuple, fn: Callable[[EcourtsClient], Any]) -> Any:
        hit = self._cache.get(key)
        if hit and hit[0] > time.time():
            return hit[1]
        with self._lock:
            for attempt in range(2):
                try:
                    if self._client is None:
                        self._client = _new_client()
                    value = fn(self._client)
                    break
                except (SessionExpired, PortalUnavailable):
                    self._client = None
                    if attempt:
                        raise
        # Don't cache empty lists: they are usually a transient portal hiccup.
        if value:
            self._cache[key] = (time.time() + config.META_CACHE_TTL, value)
        return value

    def states(self):
        return self._call(("states",), lambda c: _options(
            str(BeautifulSoup(c.landing_html, "lxml").find("select", id="sess_state_code") or "")))

    def districts(self, state: str):
        return self._call(("dist", state), lambda c: _options(
            c.post("casestatus/fillDistrict", {"state_code": state}).get("dist_list")))

    def complexes(self, state: str, dist: str):
        def fn(c):
            opts = _options(c.post("casestatus/fillcomplex", {"state_code": state, "dist_code": dist}).get("complex_list"))
            for o in opts:
                code, ests, needs = _split_complex(o["value"])
                o.update(code=code, establishment_codes=ests, requires_establishment=needs)
            return opts
        return self._call(("cx", state, dist), fn)

    def establishments(self, state: str, dist: str, court_complex: str):
        code, _, _ = _split_complex(court_complex)
        return self._call(("est", state, dist, code), lambda c: _options(c.post(
            "casestatus/fillCourtEstablishment",
            {"state_code": state, "dist_code": dist, "court_complex_code": code}).get("establishment_list")))

    def case_types(self, state: str, dist: str, court_complex: str, est: str | None):
        code, _, needs = _split_complex(court_complex)
        est = (est or "") if needs else ""

        def fn(c):
            c.post("casestatus/set_data", {"complex_code": court_complex, "selected_state_code": state,
                                           "selected_dist_code": dist, "selected_est_code": est})
            return _options(c.post("casestatus/fillCaseType", {
                "state_code": state, "dist_code": dist, "court_complex_code": code,
                "est_code": est, "search_type": "c_no"}).get("casetype_list"))
        return self._call(("ct", state, dist, code, est), fn)


meta = _MetaService()
