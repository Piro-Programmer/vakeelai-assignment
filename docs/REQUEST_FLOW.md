# eCourts v6: reverse-engineered request flow

This document records what the portal (`https://services.ecourts.gov.in/ecourtindia_v6/`)
does behind the scenes. It was worked out by running both searches in DevTools
and then reading the site's own JavaScript (`components.js`, `common_header.js`,
`searchByCNR.js`, `searchByCaseStatus.js`). The scraper in `backend/app/scraper/`
replays exactly this sequence with `requests`, so no browser automation is involved.

## 1. Session bootstrap

| # | Request | Purpose |
|---|---------|---------|
| 1 | `GET /ecourtindia_v6/` | Sets cookies `SERVICES_SESSID` (PHP session, path `/ecourtindia_v6`) and `JSESSION`. |
| 2 | `GET /ecourtindia_v6/?p=casestatus/index` | Returns HTML with `<input id="app_token" value="<64-hex>">`. |
| 3 | `GET /ecourtindia_v6/js/components.js?v=<ts>` | Holds the rotating anti-bot header pair (see below). |

**Gotcha 1: the token is not on the homepage.** For a fresh session the bare
homepage renders `app_token value=""`. Every AJAX call made with an empty token gets
`"Invalid Request"`. The `?p=casestatus/index` page *does* embed a valid token.

**Gotcha 2: rotating custom headers.** `ajaxCall()` in `components.js` sends:

```js
var delimeter = "sjhrt654";             // value changes per deploy/version
headers: { "delimeter": delimeter, "Cgfhfhgrt65": delimeter }   // name changes too
```

Requests without these headers fail with `"Invalid Request"`, even with valid cookies
and token. Both the header **name** and **value** change whenever the `?v=` timestamp
changes (I saw three different pairs in one day). The scraper therefore downloads the
exact `components.js?v=…` that the bootstrap page references and pulls out the pair with
a regex scoped to the body of `ajaxCall()`.

## 2. AJAX conventions (all endpoints)

* `POST /ecourtindia_v6/?p=<module>/<action>`, form-encoded.
* Body always ends with `&ajax_req=true&app_token=<token>`.
* Headers: the rotating pair above, plus `X-Requested-With: XMLHttpRequest`.
* The response is JSON and **always carries a new `app_token`**, which must be used on the
  next call. Error responses carry one too. The token is a strictly sequential chain, so
  one session must never make two calls in parallel.
* Errors arrive as HTTP 200 with `{"errormsg": "...", "app_token": "..."}`:
  `Invalid Captcha...`, `Session timeout..!!!`, `Invalid Request...`.

## 3. Captcha

* Image: `GET /ecourtindia_v6/vendor/securimage/securimage_show.php?<random>` (PHP Securimage).
* The answer is stored in the PHP session, so the image **must** be fetched with the same
  cookies that will submit it.
* Solved with `ddddocr` (ONNX OCR, typically 1-3 tries) inside a retry loop. If OCR keeps
  failing, the session is parked server-side and the UI shows the image for manual entry.

## 4. CNR search

```
POST ?p=cnr_status/searchByCNR/   cino=DLND020000602007  fcaptcha_code=<answer>
→ { "casetype_list": "<full case HTML>", "status": "1", "app_token": ... }
```

## 5. Case-number search

Cascading dropdowns (no captcha):

| Endpoint | Params | Returns |
|---|---|---|
| state list | (embedded in bootstrap HTML `select#sess_state_code`) | Delhi = `26` |
| `casestatus/fillDistrict` | `state_code` | `dist_list` HTML options (South = `10`) |
| `casestatus/fillcomplex` | `state_code, dist_code` | `complex_list`: value `1260011@1,2,3,4@Y` = *complex code @ establishment codes @ "establishment must be chosen" flag* |
| `casestatus/fillCourtEstablishment` | `state_code, dist_code, court_complex_code` | `establishment_list` (DJ South Saket = `1`) |
| `casestatus/set_data` | `complex_code (raw), selected_state_code, selected_dist_code, selected_est_code` | pins the court in the session |
| `casestatus/fillCaseType` | `state_code, dist_code, court_complex_code, est_code, search_type=c_no` | `casetype_list` (CS (COMM) = `77^1`) |

Search (captcha):

```
POST ?p=casestatus/submitCaseNo
  case_type=77^1 search_case_no=233 rgyear=2024 case_captcha_code=<answer>
  state_code=26 dist_code=10 court_complex_code=1260011 est_code=1 case_no=233
→ { "case_data": "<result table HTML>" }
```

Each result row has `onClick="viewHistory(207700002332024,'DLST010047302024',1,'','CScaseNumber',26,10,1260011,'CScaseNumber')"`.

## 6. Case details / hearings / orders (no captcha)

```
POST ?p=home/viewHistory
  court_code state_code dist_code court_complex_code case_no cino hideparty search_flag search_by
→ { "data_list": "<full case HTML>" }        # same layout as the CNR result

POST ?p=home/viewBusiness      (per hearing; args from onclick=viewBusiness(...))
  court_code dist_code nextdate1 case_number1 state_code disposal_flag businessDate
  court_no national_court_code search_by srno [court_complex_code]

POST ?p=home/display_pdf       (per order; args from onclick=displayPdf(...))
  normal_v case_val court_code filename appFlag
→ { "order": "reports/<random>.pdf" }   → GET /ecourtindia_v6/reports/<random>.pdf
```

**Gotcha 3: display_pdf is session-stateful.** On a cold session it returns
`Session timeout`. It only works after the *same* session has opened the case through
`viewHistory`. `viewHistory` needs no captcha and works with just
`cino + state/district/court codes`, and those codes are on every case page inside the
"View QR Code" link (`home/case_acknowlegement&cino=…&state_code=…&dist_code=…&court_code=…`).
So the PDF proxy does: fresh session → `viewHistory` (warm-up) → `display_pdf` → `GET pdf`.

## 7. HTML quirks handled by the parser

* `Vs</br>` (an invalid closing br tag) between party names. lxml drops it and glues the names together.
* The "Processes" table puts `<td>`s straight inside `<thead>` with no `<tr>`.
* Several parties inside one `<li>`, separated by `<br>` and `2)` counters; advocates on
  `Advocate- NAME` lines.
* Case Status rows use `<td><strong>` as labels instead of `<th>`.
