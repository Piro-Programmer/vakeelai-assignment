# VakeelAI: eCourts Case Scraper & Legal Draft Generator

Two tools behind one FastAPI + React app:

1. **District Court case scraper** looks up any case on the
   [eCourts portal](https://services.ecourts.gov.in/ecourtindia_v6/) by **CNR number** or by
   **State → District → Court Complex → Establishment → Case Type → Number → Year**. It returns
   everything the portal shows as clean JSON: case details, filing/registration, status, parties
   and advocates, acts, FIR, hearing history (with per-hearing daily status), interim and final
   orders (with downloadable PDFs), processes and transfers.
2. **Legal draft generator** is a rule-based drafting engine in pure Python (no LLMs, no external
   APIs). It produces a Legal Notice, a Money Recovery Plaint, a Bail Application or an Affidavit
   from a form, with a live preview and export to **Word (.docx)** and **PDF**.

> **Live app:** _<add Render URL here>_  ·  **API docs:** `<live-url>/docs`

---

## How the scraper works (short version)

No browser automation. The scraper replays the portal's own AJAX calls with `requests`.
The full reverse-engineering notes are in **[docs/REQUEST_FLOW.md](docs/REQUEST_FLOW.md)**.

```
GET /                         → session cookies
GET ?p=casestatus/index       → first app_token (NOT present on the homepage)
GET js/components.js?v=…      → rotating anti-bot header name+value, extracted by regex
GET securimage_show.php       → captcha → ddddocr OCR (retry ≤ 8×, then manual fallback)
POST ?p=cnr_status/searchByCNR          (CNR)        ┐ each response rotates app_token
POST ?p=casestatus/submitCaseNo         (case no.)   │
POST ?p=home/viewHistory / viewBusiness / display_pdf┘
```

Three non-obvious findings shaped the design:

| Finding | Consequence |
|---|---|
| The token lives on `?p=casestatus/index`, not the homepage | Bootstrap from that page |
| Every AJAX call needs a custom header pair (e.g. `Cgfhfhgrt65: sjhrt654`) whose name **and** value rotate with each JS version | Parse it from the live `components.js` every session and never hardcode it |
| `display_pdf` only works after the same session has opened the case | The PDF proxy warms up the session with a captcha-free `viewHistory` |

## Repository layout

```
backend/
  app/
    main.py                 FastAPI app (also serves the built frontend)
    config.py               env-driven settings
    api/cases.py            /api/meta/*, /api/cases/*
    api/drafts.py           /api/drafts/*
    scraper/
      client.py             session, token rotation, anti-bot headers, error mapping
      captcha.py            ddddocr OCR + normalisation
      service.py            search flows, captcha retry/fallback, dropdown cache
      parser.py             HTML → structured JSON (heading-driven, defensive)
      refs.py               HMAC-signed stateless links for PDFs / hearing details
      session_store.py      parked sessions for manual captcha (TTL + cap)
      errors.py             typed exceptions → HTTP codes
    drafts/
      schemas.py            field schemas (drive validation AND the React form)
      engine.py             validate → enrich → Jinja2 → block markup → blocks
      templates/*.j2        the four legal templates
      exporters.py          blocks → HTML / DOCX / PDF
      utils.py              ₹ formatting, amount in words (lakh/crore), legal dates, interest
  fixtures/                 real portal responses used by the tests
  tests/                    pytest suite (35 tests, offline)
frontend/                   React 19 + Vite + TypeScript + Tailwind v4
docs/REQUEST_FLOW.md        reverse-engineered request flow
Dockerfile, render.yaml     single-service deployment
```

## Running locally

**Prerequisites:** Python 3.10+ (developed on 3.13; the Docker image uses 3.12) and Node 18+.

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Frontend (dev mode, hot reload)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to the backend on port 8000.

### Single-server mode (what production runs)

```bash
cd frontend && npm run build    # creates frontend/dist
cd ../backend && uvicorn app.main:app --port 8000
```

FastAPI serves the built app at http://localhost:8000.

### Tests

```bash
cd backend
pytest -q
```

The tests run offline against captured portal responses in `backend/fixtures/`.

### Environment variables (all optional)

| Var | Default | Purpose |
|---|---|---|
| `OCR_ATTEMPTS` | `8` | OCR tries before asking the user to type the captcha |
| `CAPTCHA_SESSION_TTL` | `600` | Seconds a manual-captcha search stays resumable |
| `SECRET_KEY` | random per process | Signs PDF/hearing links. Set it so links survive restarts |
| `ECOURTS_PROXY` | – | Outbound HTTP(S) proxy, e.g. an Indian IP if the host is geo-blocked |
| `CORS_ORIGINS` | `*` | Only needed when the frontend is hosted separately |
| `VITE_API_URL` | (same origin) | Frontend build-time API base, for split hosting |

## Deployment

The `Dockerfile` builds the frontend and serves it from FastAPI, so the whole project runs as
**one service** with one URL and no CORS.

**Render:** New → Blueprint → select this repo (`render.yaml`, region Singapore, free plan).
Any Docker host works the same way (Railway, Fly.io, Hugging Face Spaces with Docker).

## API reference

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/api/meta/states` | – | `[{value,label}]` |
| GET | `/api/meta/districts` | `state` | options |
| GET | `/api/meta/complexes` | `state, district` | options + `code, establishment_codes, requires_establishment` |
| GET | `/api/meta/establishments` | `state, district, complex` | options |
| GET | `/api/meta/case-types` | `state, district, complex, establishment` | options |
| POST | `/api/cases/cnr` | `{cnr}` | `{status:"ok", type:"case", case}` or `captcha_required` |
| POST | `/api/cases/case-number` | `{state_code, dist_code, court_complex, est_code, case_type, case_number, year}` | `{type:"matches", matches:[{title, cnr, detail_ref…}]}` or `captcha_required` |
| POST | `/api/cases/captcha` | `{search_id, code}` | resumes the parked search |
| POST | `/api/cases/detail` | `{detail_ref}` | full case |
| GET | `/api/cases/business` | `ref` | daily status of one hearing |
| GET | `/api/cases/order-pdf` | `ref` | the order/judgment PDF (proxied) |
| GET | `/api/drafts/templates` | – | template schemas + sample data |
| POST | `/api/drafts/render` | `{template, data}` | `{blocks, html, word_count}`, or 422 with per-field errors |
| POST | `/api/drafts/export/{docx\|pdf\|html}` | `{template, data}` | file |

Errors from the scraper use one shape: `{"status":"error","error":"CaptchaError|CaseNotFound|…","message":…}`.

<details>
<summary><b>Sample output</b>: CS (COMM)/233/2024, Saket (abridged)</summary>

```json
{
  "court_name": "District and Sessions Judge, South , Saket",
  "summary": {
    "cnr": "DLST010047302024",
    "title": "Punjab National Bank vs Sunil Kumar",
    "case_type": "CS (COMM) - CIVIL SUIT (COMMERCIAL)",
    "registration_number": "233/2024",
    "is_disposed": true,
    "decision_date": "03rd June 2025",
    "stage": "Case disposed"
  },
  "case_details": {
    "case_type": "CS (COMM) - CIVIL SUIT (COMMERCIAL)",
    "filing_number": "2605/2024", "filing_date": "09-05-2024",
    "registration_number": "233/2024", "registration_date": "10-05-2024",
    "cnr_number": "DLST010047302024",
    "efiling_number": "ADL20230009084C202400007", "efiling_date": "09-05-2024"
  },
  "case_status": {
    "first_hearing_date": "10th May 2024", "decision_date": "03rd June 2025",
    "status": "Case disposed", "nature_of_disposal": "Uncontested--DECREED",
    "court_number_and_judge": "770-District Judge (Commercial Court) - 01"
  },
  "petitioners": [{ "name": "Punjab National Bank", "advocates": ["DINANATH THAKUR"], "details": null }],
  "respondents": [{ "name": "Sunil Kumar", "advocates": [], "details": null }],
  "acts": [{ "act": null, "sections": "6" }],
  "processes": [{ "process_id": "PDLST010047302024_1_1", "process_title": "Summons for settlement of issues [O. 5, R. 1, 5.]", "process_date": "17-05-2024" }],
  "hearing_history": [
    { "judge": "District Judge (Commercial Court) - 01", "business_on_date": "03-06-2025",
      "hearing_date": null, "purpose_of_hearing": "Disposed", "business_url": "/api/cases/business?ref=…" }
  ],
  "final_orders": [
    { "order_number": "9", "order_date": "03-06-2025", "order_details": "COPY OF JUDGMENT",
      "pdf_url": "/api/cases/order-pdf?ref=…" }
  ],
  "source": { "portal": "https://services.ecourts.gov.in/ecourtindia_v6/", "fetched_at": "2026-10-27T10:42:57+00:00" }
}
```
</details>

## Design decisions & trade-offs

**Scraper**
- **`requests` instead of Selenium/Playwright.** It's lighter (fits a 512 MB free instance), faster
  and deterministic. In return, the token and header rules must be reproduced by hand. That logic
  is isolated in `client.py`.
- **Captcha: OCR first, human second.** `ddddocr` is pip-only, needs no system binaries and is
  accurate on Securimage. A bad guess costs one round trip, so we retry with fresh images. If OCR
  keeps failing, the live session is *parked*, because a captcha is only valid for the session
  that rendered it, and the user types the answer. The search never dead-ends.
- **Stateless follow-up links.** Hearing details and PDFs need the portal's encrypted
  `onclick` arguments. Rather than keep sessions in RAM, those arguments go into an
  **HMAC-signed** token in the URL. Links survive restarts (with a fixed `SECRET_KEY`), and the
  endpoint can't be abused as an open relay to the portal.
- **Parser keys sections by `<h3>` heading, not position.** Criminal, civil, pending and disposed
  cases show different sections. Unknown sections still come back under `other_sections`, so
  nothing the portal shows is silently dropped.
- **Shared, cached session for dropdowns.** Dropdown lookups need no captcha, so one long-lived
  session (lock-serialised, because the token is a chain) plus a 6 h cache keeps the cascading
  selects fast.
- **One worker.** Parked captcha sessions live in process memory. The scale-out path would be
  Redis, which this project's scale doesn't need.

**Drafts**
- **Templates → block markup → renderers.** Jinja2 templates emit simple directives (`@num`,
  `@heading`, `@sub`…). One parsed block list feeds the HTML preview, DOCX and PDF, so all three
  always match, and templates stay readable and editable without touching Python.
- **Schema-driven forms.** `schemas.py` drives both server validation and the React form, so
  adding a template needs no frontend code.
- **Legal-language details in code, not templates:** Indian digit grouping and lakh/crore words,
  "27th day of October, 2026", actual/365 simple interest, plural roles and verb agreement
  ("the Defendants are"), "That the…" capitalisation that keeps proper nouns, BNSS↔CrPC
  section mapping, and an auto-filled "paragraphs 1 to N" in the verification.
- **PDF uses "Rs."** The built-in PDF fonts lack the ₹ glyph, and embedding a TTF for one
  character wasn't worth it. DOCX keeps ₹.

## Known limitations

- **Geo/IP blocking.** eCourts may throttle or block some non-Indian datacenter IPs. The
  deployment uses Render's Singapore region (closest to India). If the portal blocks the host,
  set `ECOURTS_PROXY` to an Indian proxy. Run locally, the app works from any Indian connection.
- The portal's HTML and anti-bot rules can change without notice. Tests run against captured
  fixtures so regressions are easy to spot, and the request flow is all in one module.
- Generated drafts are starting points and must be reviewed by an advocate before filing.
  Court fees and some state-specific formalities are left as blanks to fill in.
