"""
HTML -> structured data for eCourts case pages.

The portal returns ready-made HTML fragments inside its JSON (`casetype_list`
for CNR, `data_list` for viewHistory). Design choices:

* **Sections are located by their <h3> heading text, not by position.** Which
  sections appear depends on the case: criminal cases have "FIR Details", some
  have "Processes", "Subordinate Court", "IA Status", etc., and disposed cases
  add "Final Orders / Judgements". Matching on headings makes the parser
  indifferent to order and to missing sections.

* **Known sections get a curated schema** (stable snake_case keys a frontend
  can rely on). **Unknown sections are still captured generically** under
  `other_sections`, so if the portal adds a table we don't silently drop data.
  The assignment asks for "everything the portal shows", and this is the
  safety net for that.

* **Links are captured as opaque refs.** Order PDFs and daily-business pages
  are behind `onclick=displayPdf(...)` / `viewBusiness(...)` JS calls with
  encrypted arguments. We keep those exact arguments; the API wraps them in a
  URL-safe token so the frontend can fetch the PDF later, statelessly.

* **Defensive by default:** every section parser tolerates absence, and
  whitespace and `&nbsp;` noise are normalised in one place (`_clean`).
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag

# ---------------------------------------------------------------- utilities
_WS = re.compile(r"\s+")
_JS_ARGS = re.compile(r"(\w+)\(([^)]*)\)")


def _clean(text: str | None) -> str:
    return _WS.sub(" ", (text or "").replace("\xa0", " ")).strip()


def _soup(html: str) -> BeautifulSoup:
    """Parse portal HTML after fixing its most damaging quirk.

    The portal writes `Vs</br>` (a closing br tag). lxml drops it, which glues
    "Vs" onto the next party name ("VsSunil Kumar"), so it is rewritten to
    a real <br/> first.
    """
    return BeautifulSoup(re.sub(r"</br\s*>", "<br/>", html, flags=re.I), "lxml")


def _slug(label: str) -> str:
    """'Court Number and Judge' -> 'court_number_and_judge'."""
    s = re.sub(r"[^a-z0-9]+", "_", _clean(label).lower()).strip("_")
    return s or "field"


def _none_if_blank(v: str) -> str | None:
    v = _clean(v)
    return None if v in ("", "-", "--", "---", "NA", "N/A") else v


def parse_js_call(onclick: str | None) -> tuple[str, list[str]] | None:
    """`viewBusiness('2','7','2026')` -> ('viewBusiness', ['2','7','2026']).

    The argument strings are base64-ish (may contain '/', '+', '='), never
    commas, so a plain comma split is safe here. Quotes are stripped.
    """
    if not onclick:
        return None
    m = _JS_ARGS.search(onclick)
    if not m:
        return None
    args = [a.strip().strip("'\"") for a in m.group(2).split(",")] if m.group(2).strip() else []
    return m.group(1), args


# ----------------------------------------------------------- section finder
def _sections(soup: BeautifulSoup) -> dict[str, Tag]:
    """Map each <h3> heading (slugified) to the first table/ul after it.

    find_next() walks the document in order, so we stop if the next
    heading comes first: that section has a heading but no body.
    """
    out: dict[str, Tag] = {}
    for h in soup.find_all("h3"):
        title = _slug(h.get_text())
        if not title or title in out:
            continue
        body = h.find_next(["table", "ul", "h3"])
        if body is not None and body.name != "h3":
            out[title] = body
    return out


# ------------------------------------------------------- generic table shapes
def _kv_table(table: Tag) -> dict[str, str | None]:
    """Label/value tables (Case Details, Case Status, FIR Details).

    Rows look like `<th>Label</th><td>Value</td>[<th>Label2</th><td>Value2</td>]`,
    but the portal sometimes uses <td><strong> for labels (Case Status rows).
    So we read cells pairwise, whatever their tag. A row with an odd cell
    count (e.g. the CNR row with an extra "View QR code" link cell) keeps
    its first pair and drops the trailing extra.
    """
    data: dict[str, str | None] = {}
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
        # "Field | Details" header row on FIR tables carries no data
        if all(c.name == "th" for c in cells) and len(cells) == 2 and _clean(cells[0].get_text()).lower() == "field":
            continue
        for i in range(0, len(cells) - 1, 2):
            key = _slug(cells[i].get_text())
            # Drop the "(Note the CNR number ...)" hint inside the CNR cell
            for em in cells[i + 1].find_all("em"):
                em.decompose()
            data[key] = _none_if_blank(cells[i + 1].get_text(" "))
    return data


def _grid_table(table: Tag) -> list[dict[str, Any]]:
    """Header + rows tables (history, orders, transfers, processes).

    Each row becomes a dict keyed by the slugified header. If a cell holds a
    JS link we keep it under `_links` so the caller can turn it into a ref.
    """
    header_cells = table.find("thead")
    headers: list[str] = []
    if header_cells:
        headers = [_slug(th.get_text()) for th in header_cells.find_all("th")]
    rows = []
    for tr in table.find_all("tr"):
        if tr.find_parent("thead"):
            continue
        cells = tr.find_all("td", recursive=False)
        if not cells:
            # header row not wrapped in <thead>
            ths = tr.find_all("th", recursive=False)
            if ths and not headers:
                headers = [_slug(th.get_text()) for th in ths]
            continue
        row: dict[str, Any] = {}
        links = []
        for idx, td in enumerate(cells):
            key = headers[idx] if idx < len(headers) else f"col_{idx + 1}"
            row[key] = _none_if_blank(td.get_text(" "))
            a = td.find("a", onclick=True)
            if a:
                call = parse_js_call(a.get("onclick"))
                if call:
                    links.append({"column": key, "fn": call[0], "args": call[1]})
        if links:
            row["_links"] = links
        if any(v for k, v in row.items() if k != "_links"):
            rows.append(row)

    # Fallback for malformed tables. The "Processes" table puts its <td>s
    # straight inside <thead> with no wrapping <tr>, so the row walk above
    # finds nothing. Re-chunk every <td> in document order by the header count.
    if not rows and headers:
        tds = table.find_all("td")
        for i in range(0, len(tds) - len(headers) + 1, len(headers)):
            chunk = tds[i : i + len(headers)]
            row = {headers[j]: _none_if_blank(td.get_text(" ")) for j, td in enumerate(chunk)}
            if any(row.values()):
                rows.append(row)
    return rows


# --------------------------------------------------------------- parties
_ADV_SPLIT = re.compile(r"\s*Advocate\s*[-:]\s*", re.I)
_PARTY_NUM = re.compile(r"^\s*\d+\)\s*")


def _parties(ul: Tag | None) -> list[dict[str, Any]]:
    """Parse the Petitioner/Respondent <ul>.

    The markup is messy: several parties can share ONE <li>, separated by
    <br> and a leading "2)" counter, and advocates follow their party as
    "Advocate- NAME" lines. We flatten to text lines on <br>, then walk them:
    a numbered line starts a new party, an "Advocate-" line attaches to the
    current one, and any other line is a continuation of the party (often an
    address).
    """
    if ul is None:
        return []
    for br in ul.find_all("br"):
        br.replace_with("\n")
    lines = [_clean(l) for l in ul.get_text().split("\n")]
    parties: list[dict[str, Any]] = []
    for line in filter(None, lines):
        if _ADV_SPLIT.match(line) or line.lower().startswith("advocate"):
            adv = _ADV_SPLIT.split(line, maxsplit=1)[-1].strip()
            if parties and adv:
                parties[-1]["advocates"].append(adv)
            continue
        if _PARTY_NUM.match(line) or not parties:
            parties.append({"name": _PARTY_NUM.sub("", line), "advocates": [], "details": []})
        else:
            parties[-1]["details"].append(line)
    for p in parties:
        p["details"] = " ".join(p["details"]) or None
    return parties


# ------------------------------------------------------------- public API
def _date_key_fix(d: dict[str, Any]) -> dict[str, Any]:
    """Portal labels vary a little ('e-Filing Number' vs 'eFiling Number'),
    so normalise to stable names the frontend can depend on."""
    renames = {"e_filing_number": "efiling_number", "e_filing_date": "efiling_date", "case_status": "status"}
    return {renames.get(k, k): v for k, v in d.items()}


def parse_case_history(html: str) -> dict[str, Any]:
    """Parse a full case page (CNR result or viewHistory data_list)."""
    soup = _soup(html)
    sec = _sections(soup)
    used: set[str] = set()

    def take(*names: str) -> Tag | None:
        for n in names:
            if n in sec:
                used.add(n)
                return sec[n]
        return None

    heading = soup.find("h2", id="chHeading") or soup.find("h2")
    result: dict[str, Any] = {"court_name": _clean(heading.get_text()) if heading else None}

    # The "View QR Code / Cause Title" link carries the case's internal court
    # coordinates (cino, state, district, court, complex). They aren't shown
    # as text anywhere, but the service needs them to re-open the case on a
    # fresh session (the portal only serves order PDFs for the case that was
    # last opened in that session).
    ack = soup.find("a", onclick=re.compile(r"case_acknowlegement"))
    call = parse_js_call(ack.get("onclick")) if ack else None
    if call and call[1]:
        query = call[1][0].split("&", 1)[-1]
        result["_context"] = dict(kv.split("=", 1) for kv in query.split("&") if "=" in kv)

    t = take("case_details")
    result["case_details"] = _date_key_fix(_kv_table(t)) if t is not None else {}
    t = take("case_status")
    result["case_status"] = _date_key_fix(_kv_table(t)) if t is not None else {}
    result["petitioners"] = _parties(take("petitioner_and_advocate"))
    result["respondents"] = _parties(take("respondent_and_advocate"))

    t = take("acts")
    result["acts"] = [
        {"act": r.get("under_act_s"), "sections": r.get("under_section_s")}
        for r in (_grid_table(t) if t is not None else [])
    ]

    t = take("fir_details")
    result["fir_details"] = _kv_table(t) if t is not None else None

    t = take("case_history")
    history = []
    for r in _grid_table(t) if t is not None else []:
        item = {
            "judge": r.get("judge"),
            "business_on_date": r.get("business_on_date"),
            "hearing_date": r.get("hearing_date"),
            "purpose_of_hearing": r.get("purpose_of_hearing"),
        }
        biz = next((l for l in r.get("_links", []) if l["fn"] == "viewBusiness"), None)
        item["_business_args"] = biz["args"] if biz else None
        history.append(item)
    result["hearing_history"] = history

    def orders(tag: Tag | None) -> list[dict[str, Any]]:
        out = []
        for r in _grid_table(tag) if tag is not None else []:
            pdf = next((l for l in r.get("_links", []) if l["fn"] == "displayPdf"), None)
            out.append(
                {
                    "order_number": r.get("order_number"),
                    "order_date": r.get("order_date"),
                    "order_details": r.get("order_details"),
                    "_pdf_args": pdf["args"] if pdf else None,
                }
            )
        return out

    result["interim_orders"] = orders(take("interim_orders"))
    result["final_orders"] = orders(take("final_orders_judgements"))

    for key, names in {
        "processes": ("processes",),
        "case_transfers": ("case_transfer_details_within_establishment",),
        "subordinate_court": ("subordinate_court_information_details", "subordinate_court_information"),
        "ia_status": ("ia_status",),
        "linked_cases": ("linked_cases",),
    }.items():
        t = take(*names)
        if t is None:
            continue
        rows = _grid_table(t)
        result[key] = rows if rows else _kv_table(t)

    # Safety net: anything we didn't model explicitly is still returned.
    other = {}
    for name, tag in sec.items():
        if name not in used and name not in ("processes",):
            rows = _grid_table(tag) if tag.name == "table" else []
            other[name] = rows or (_kv_table(tag) if tag.name == "table" else _clean(tag.get_text(" ")))
    if other:
        result["other_sections"] = other
    return result


def parse_case_list(html: str) -> list[dict[str, Any]]:
    """Parse the case-number search result table into selectable matches.

    One search can return cases from several establishments of the same
    complex, so each row keeps its establishment heading plus the exact
    viewHistory() arguments needed to open it.
    """
    soup = _soup(html)
    matches = []
    establishment = None
    table = soup.find("table", id="dispTable") or soup.find("table")
    if table is None:
        return []
    for tr in table.find_all("tr"):
        th = tr.find("th", attrs={"colspan": True})
        if th:
            establishment = _clean(th.get_text())
            continue
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        a = tr.find("a", onclick=True)
        call = parse_js_call(a.get("onclick") if a else None)
        if not call or call[0] != "viewHistory":
            continue
        parties_td = tds[2]
        for br in parties_td.find_all("br"):
            br.replace_with("\n")
        party_lines = [p for p in (_clean(x) for x in parties_td.get_text().split("\n")) if p]
        vs = [p for p in party_lines if p.lower() not in ("vs", "versus")]
        args = call[1]
        matches.append(
            {
                "sr_no": _clean(tds[0].get_text()),
                "establishment": establishment,
                "case_number": _clean(tds[1].get_text()),
                "petitioner": vs[0] if vs else None,
                "respondent": vs[1] if len(vs) > 1 else None,
                "title": " vs ".join(vs[:2]),
                "cnr": args[1] if len(args) > 1 else None,
                "_history_args": args,
            }
        )
    return matches


def parse_business(html: str) -> dict[str, Any]:
    """Parse the 'Daily Status' popup (viewBusiness) into label/value pairs."""
    soup = _soup(html)
    out: dict[str, Any] = {}
    for span in soup.find_all("span"):
        b = span.find("b")
        if b and ":" in span.get_text():
            label, _, value = span.get_text().partition(":")
            out[_slug(label)] = _none_if_blank(value)
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) >= 3:
            out[_slug(tds[0].get_text())] = _none_if_blank(tds[2].get_text(" "))
    return out
