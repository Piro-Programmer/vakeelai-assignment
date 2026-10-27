import datetime as dt
from decimal import Decimal

import pytest

from app.drafts import utils
from app.drafts.engine import DraftValidationError, generate, lc_first, parse_blocks
from app.drafts.exporters import to_docx, to_pdf
from app.drafts.schemas import TEMPLATES, defaults_for


@pytest.mark.parametrize("n,words", [
    (0, "Zero"),
    (15, "Fifteen"),
    (105, "One Hundred Five"),
    (1_00_000, "One Lakh"),
    (12_50_000, "Twelve Lakh Fifty Thousand"),
    (1_23_45_678, "One Crore Twenty Three Lakh Forty Five Thousand Six Hundred Seventy Eight"),
    (100_00_00_000, "One Hundred Crore"),
])
def test_indian_number_words(n, words):
    assert utils.number_to_words_indian(n) == words


def test_money_formatting():
    assert utils.format_inr(1250000) == "₹12,50,000"
    assert utils.format_inr("1,00,000.5") == "₹1,00,000.50"
    assert utils.amount_in_words(1250000.5) == "Rupees Twelve Lakh Fifty Thousand and Paise Fifty Only"


def test_dates_and_ordinals():
    assert utils.legal_date("2026-10-01") == "1st day of October, 2026"
    assert utils.legal_date("2026-10-12") == "12th day of October, 2026"  # teen exception
    assert utils.short_date("2026-10-27") == "27.10.2026"


def test_simple_interest_actual_365():
    # 10L @ 12% for 365 days = 1.2L
    assert utils.simple_interest(1000000, 12, "2025-01-01", "2026-01-01") == Decimal("120000.00")
    assert utils.simple_interest(1000000, 12, "2026-01-01", "2025-01-01") == 0  # reversed dates -> no negative interest


def test_lc_first_keeps_proper_nouns():
    assert lc_first("The Defendant failed") == "the Defendant failed"
    assert lc_first("Punjab National Bank sanctioned") == "Punjab National Bank sanctioned"
    assert lc_first("FIR was lodged") == "FIR was lodged"


def test_block_numbering():
    blocks = parse_blocks("@num a\n@num b\n@sub x\n@sub y\n@para p\n@sub z\n@para 1 to __LAST_PARA__")
    assert [b.label for b in blocks] == ["1.", "2.", "(a)", "(b)", None, "(a)", None]
    assert blocks[-1].text == "1 to 2"


@pytest.mark.parametrize("tid", list(TEMPLATES))
def test_every_template_renders_and_exports(tid):
    draft = generate(tid, defaults_for(tid))
    assert draft["blocks"] and draft["word_count"] > 100
    text = " ".join(b["text"] for b in draft["blocks"])
    # No template leakage: unrendered Jinja or a directive that failed to parse.
    # ("@ 12%" inside a sentence is legitimate, so only block starts are checked.)
    assert "{{" not in text and not any(b["text"].startswith("@") for b in draft["blocks"])
    assert to_docx(draft)[:2] == b"PK"
    assert to_pdf(draft)[:4] == b"%PDF"


def test_suit_maths_and_grammar():
    data = defaults_for("money_recovery_suit")
    data.update(date="2024-06-01", interest_from="2023-06-01", principal_amount=1000000, interest_rate=12)
    data["defendants"] = data["defendants"] * 2
    text = " ".join(b["text"] for b in generate("money_recovery_suit", data)["blocks"])
    # 2023-06-01 -> 2024-06-01 is 366 days (leap year): 10,00,000 x 12% x 366/365 = 1,20,328.77
    assert "₹11,20,328.77" in text
    assert "Defendants" in text and "jointly and severally" in text


def test_validation_collects_all_errors():
    with pytest.raises(DraftValidationError) as exc:
        # A fully blank party row is ignored by design (an untouched "add party" card),
        # so give this one an address to make the missing name a real error.
        generate("bail_application", {"applicants": [{"name": "", "address": "Delhi"}], "advocate_name": ""})
    errs = exc.value.errors
    assert "applicants.0.name" in errs and "fir_number" in errs and "advocate_name" in errs


def test_user_text_is_escaped_in_html():
    from app.drafts.exporters import to_html
    data = defaults_for("affidavit")
    data["statements"] = ["<script>alert(1)</script>"]
    html = to_html(generate("affidavit", data), standalone=False)
    assert "<script>" not in html and "&lt;script&gt;" in html
