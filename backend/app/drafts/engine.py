"""
Draft engine: validate -> enrich -> render template -> structured blocks.

Architecture (no LLMs, deterministic):

    user input --validate()--> clean data --enrich()--> context
        --Jinja2 template--> block markup --parse_blocks()--> [Block, ...]
        --> renderers (HTML preview, DOCX, PDF)

Why the intermediate "block markup"? Templates must render to three formats.
If templates emitted HTML, DOCX output would need an HTML->Word converter
(lossy, a heavy dependency). If they emitted python-docx calls, the
templates would become code. Instead each template line starts with a tiny
directive:

    @court   IN THE COURT OF ...        centred, bold, upper-case
    @title   SUIT FOR RECOVERY OF ...   centred, bold, underlined
    @center  text                       centred
    @heading FACTS OF THE CASE          bold section heading
    @num     paragraph                  auto-numbered 1., 2., 3. ...
    @sub     paragraph                  lettered (a), (b) ... (restarts each run)
    @para    paragraph                  justified body text
    @left / @right  text                alignment helpers (signatures, "...Plaintiff")
    @space                              vertical gap
    @pagebreak                          new page (verification/affidavit)
    @rule                               horizontal line (letterhead)

Lines without a directive continue the previous block, so long paragraphs
can wrap naturally in the template file. Jinja2 provides loops and
conditionals, and the directives provide structure. Renderers only ever see
a list of typed blocks, so all three formats look the same.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from . import utils
from .schemas import TEMPLATES


class DraftValidationError(Exception):
    def __init__(self, errors: dict[str, str]):
        super().__init__("Invalid draft input")
        self.errors = errors


@dataclass
class Block:
    kind: str
    text: str
    label: str | None = None  # "1." / "(a)" for numbered kinds


# ------------------------------------------------------------------ jinja env
_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    # StrictUndefined: a typo in a template variable fails loudly in tests
    # instead of silently printing an empty string into a court document.
    undefined=StrictUndefined,
    # trim_blocks stays OFF: it would also eat the newline after an inline
    # `{% endif %}` and glue two directives onto one line. The blank lines that
    # block-only lines leave behind are harmless, because parse_blocks skips them.
    trim_blocks=False,
    lstrip_blocks=True,
    autoescape=False,  # output is block markup, not HTML; escaping happens in the HTML renderer
)
_env.filters.update(
    inr=utils.format_inr,
    words=utils.amount_in_words,
    legal_date=utils.legal_date,
    short_date=utils.short_date,
    num_words=lambda n: utils.number_to_words_indian(int(n or 0)),
)


def _plural(word: str, n: int) -> str:
    """Role names in pleadings: Plaintiff -> Plaintiffs, Addressee -> Addressees."""
    return word if n == 1 else word + "s"


def _party_line(p: dict[str, Any]) -> str:
    """'Sunil Kumar, S/o Ram Kumar, aged about 42 years, R/o H.No. 12 ...'.

    Optional parts are dropped cleanly, so a company party reads
    'Punjab National Bank, a body corporate ..., having its office at ...'.
    """
    parts = [p["name"].strip()]
    if p.get("parentage"):
        parts.append(p["parentage"].strip())
    if p.get("age"):
        parts.append(f"aged about {p['age']} years")
    if p.get("description"):
        parts.append(p["description"].strip())
    addr = " ".join(str(p.get("address", "")).split())
    if addr:
        # Individuals "reside at", organisations "have their office at". The
        # description/parentage is a cheap but reliable signal.
        prefix = "R/o" if p.get("parentage") or p.get("age") else "having its office at"
        parts.append(f"{prefix} {addr}")
    return ", ".join(parts)


_env.globals.update(plural=_plural, party_line=_party_line, join_names=utils.join_names)
_env.filters["lc_first"] = lambda t: lc_first(t)


# ---------------------------------------------------------------- validation
def _validate(template_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Check the input against the schema. Returns cleaned data or raises with
    EVERY error at once (better UX than fixing one field per submit)."""
    schema = TEMPLATES[template_id]
    errors: dict[str, str] = {}
    clean: dict[str, Any] = {}

    for section in schema["sections"]:
        for f in section["fields"]:
            name, ftype = f["name"], f["type"]
            raw = data.get(name, f.get("default"))
            if raw == "today":
                raw = dt.date.today().isoformat()

            if ftype == "list":
                # Accept a list or a newline-separated string; drop blank rows
                # (users often leave an empty "add another" row in the form).
                items = raw if isinstance(raw, list) else str(raw or "").splitlines()
                value = [" ".join(str(i).split()) for i in items if str(i).strip()]
                value = [_strip_leading_that(v) for v in value]
            elif ftype == "parties":
                value = []
                for idx, p in enumerate(raw or []):
                    if not isinstance(p, dict) or not any(str(v).strip() for v in p.values() if v is not None):
                        continue
                    party = {k: (str(v).strip() if v is not None else "") for k, v in p.items()}
                    if not party.get("name"):
                        errors[f"{name}.{idx}.name"] = "Party name is required"
                    if not party.get("address"):
                        errors[f"{name}.{idx}.address"] = "Party address is required"
                    if party.get("age") and not str(party["age"]).isdigit():
                        errors[f"{name}.{idx}.age"] = "Age must be a whole number"
                    value.append(party)
            elif ftype in ("money", "number"):
                value = utils.to_decimal(raw)
                if raw not in (None, "") and value is None:
                    errors[name] = "Must be a number"
                elif value is not None and value < 0:
                    errors[name] = "Cannot be negative"
            elif ftype == "date":
                value = utils.parse_date(raw)
                if raw and value is None:
                    errors[name] = "Use YYYY-MM-DD"
            elif ftype == "checkbox":
                value = raw in (True, "true", "on", "1", 1)
            elif ftype == "select":
                value = raw
                if raw and f.get("options") and raw not in f["options"]:
                    errors[name] = "Choose one of the listed options"
            else:
                value = " ".join(str(raw).split()) if f["type"] == "text" and raw is not None else (raw or "")

            empty = value in (None, "", [])
            if f.get("required") and empty and name not in errors:
                errors[name] = "This field is required"
            if isinstance(value, list):
                if f.get("min_items") and len(value) < f["min_items"] and name not in errors:
                    errors[name] = f"Add at least {f['min_items']}"
                if f.get("max_items") and len(value) > f["max_items"]:
                    errors[name] = f"At most {f['max_items']} allowed"
            clean[name] = value

    if errors:
        raise DraftValidationError(errors)
    return clean


_LC_STARTERS = {"the", "a", "an", "as", "it", "this", "that", "these", "those", "on", "in", "at", "by",
                "after", "since", "despite", "thereafter", "accordingly", "however", "further", "upon"}


def lc_first(text: str) -> str:
    """'The Defendant ...' -> 'the Defendant ...' for use after 'That '.

    Only common function words are lower-cased. Proper nouns ('Punjab
    National Bank ...') and acronyms ('FIR ...') must keep their capitals,
    so blindly lower-casing the first letter would be wrong.
    """
    first, _, rest = text.partition(" ")
    if first.lower().strip(",") in _LC_STARTERS and not first.isupper():
        return first.lower() + (" " + rest if rest else "")
    return text


def _strip_leading_that(text: str) -> str:
    """Templates add their own 'That ...' prefix where the style needs it, so a
    user-typed 'That' is removed to avoid 'That that ...'."""
    return re.sub(r"^\s*that\s*,?\s+", "", text, flags=re.I)


# --------------------------------------------------------------- enrichment
def _enrich(template_id: str, d: dict[str, Any]) -> dict[str, Any]:
    """Derived values: computed money, roles with grammar, formatted dates.

    Kept in Python (not in templates) so calculations are unit-testable and
    templates stay readable.
    """
    ctx = dict(d)
    ctx["today"] = dt.date.today()

    if template_id == "money_recovery_suit":
        interest = utils.simple_interest(d["principal_amount"], d.get("interest_rate") or 0,
                                         d["interest_from"], d["date"])
        ctx["interest_amount"] = interest
        ctx["total_claim"] = (d["principal_amount"] or Decimal(0)) + interest
        ctx["interest_days"] = max(((d["date"] - d["interest_from"]).days if d["interest_from"] else 0), 0)
        ctx["P"] = _plural("Plaintiff", len(d["plaintiffs"]))
        ctx["D"] = _plural("Defendant", len(d["defendants"]))
        # "The Plaintiff states" / "The Plaintiffs state": subject-verb agreement.
        ctx["P_states"] = "state" if len(d["plaintiffs"]) > 1 else "states"
        ctx["D_is"] = "are" if len(d["defendants"]) > 1 else "is"
        ctx["D_has"] = "have" if len(d["defendants"]) > 1 else "has"

    elif template_id == "legal_notice":
        ctx["you"] = "you" if len(d["recipients"]) == 1 else "you all"
        amt = d.get("amount")
        if amt and d.get("interest_rate"):
            ctx["interest_clause"] = f" together with interest @ {d['interest_rate']}% per annum from the date of default till realisation"
        else:
            ctx["interest_clause"] = ""
        ctx["client"] = "my client" if len(d["senders"]) == 1 else "my clients"
        ctx["Client"] = ctx["client"].capitalize()

    elif template_id == "bail_application":
        n = len(d["applicants"])
        ctx["A"] = _plural("Applicant", n)
        ctx["A_is"] = "are" if n > 1 else "is"
        ctx["anticipatory"] = d["bail_type"].startswith("Anticipatory")
        ctx["section"] = re.search(r"Section \d+ BNSS", d["bail_type"]).group(0)
        # Old-law equivalents help courts and readers during the CrPC -> BNSS transition.
        ctx["old_section"] = {"Section 483 BNSS": "Section 439 CrPC", "Section 480 BNSS": "Section 437 CrPC",
                              "Section 482 BNSS": "Section 438 CrPC"}.get(ctx["section"], "")
        if d.get("custody_since") and not ctx["anticipatory"]:
            ctx["custody_days"] = (d["date"] - d["custody_since"]).days
        else:
            ctx["custody_days"] = None

    elif template_id == "affidavit":
        ctx["deponent"] = d["deponents"][0]
    return ctx


# ------------------------------------------------------------------ parsing
_DIRECTIVE = re.compile(r"^@(\w+)\s?(.*)$")
_NUMBERED = {"num": "{n}.", "sub": "({a})"}


def parse_blocks(markup: str) -> list[Block]:
    blocks: list[Block] = []
    for line in markup.splitlines():
        if not line.strip():
            continue
        m = _DIRECTIVE.match(line.strip())
        if m:
            blocks.append(Block(m.group(1), m.group(2).strip()))
        elif blocks:
            blocks[-1].text = (blocks[-1].text + " " + line.strip()).strip()
        else:
            blocks.append(Block("para", line.strip()))

    # Numbering pass: @num counts through the whole document (pleading style);
    # @sub letters restart whenever a run of sub-items is interrupted.
    n, a = 0, 0
    for b in blocks:
        if b.kind == "num":
            n += 1
            b.label = f"{n}."
        if b.kind == "sub":
            a += 1
            b.label = f"({chr(96 + a)})" if a <= 26 else f"({a})"
        else:
            a = 0
        b.text = re.sub(r"\s+([,.;:])", r"\1", b.text)  # tidy spaces left by optional parts
    # Verifications cite "paragraphs 1 to N". The template can't know N before
    # rendering, so it writes a placeholder that is filled in once numbering is done.
    for b in blocks:
        b.text = b.text.replace("__LAST_PARA__", str(n))
    return blocks


# --------------------------------------------------------------- public API
def generate(template_id: str, data: dict[str, Any]) -> dict[str, Any]:
    if template_id not in TEMPLATES:
        raise DraftValidationError({"template": f"Unknown template '{template_id}'"})
    clean = _validate(template_id, data)
    ctx = _enrich(template_id, clean)
    markup = _env.get_template(f"{template_id}.j2").render(**ctx)
    blocks = parse_blocks(markup)
    return {
        "template": template_id,
        "title": TEMPLATES[template_id]["title"],
        "blocks": [asdict(b) for b in blocks],
        "word_count": sum(len(b.text.split()) for b in blocks),
    }
