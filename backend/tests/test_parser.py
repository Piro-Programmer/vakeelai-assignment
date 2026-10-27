"""Parser tests against real portal responses captured during reverse-engineering.

Testing against saved fixtures (not the live site) keeps the suite fast,
deterministic, and runnable offline or in CI, where the portal may be
unreachable or geo-blocked.
"""

import json
from pathlib import Path

import pytest

from app.scraper.parser import parse_case_history, parse_case_list, parse_js_call

FIX = Path(__file__).resolve().parents[1] / "fixtures"


def load(name, key):
    return json.loads((FIX / name).read_text(encoding="utf-8"))[key]


@pytest.fixture(scope="module")
def disposed():
    return parse_case_history(load("history_DLST010047302024.json", "data_list"))


@pytest.fixture(scope="module")
def pending():
    return parse_case_history(load("cnr_DLND020000602007.json", "casetype_list"))


def test_case_details(disposed):
    cd = disposed["case_details"]
    assert cd["cnr_number"] == "DLST010047302024"
    assert cd["registration_number"] == "233/2024"
    assert cd["filing_date"] == "09-05-2024"
    assert cd["efiling_number"] == "ADL20230009084C202400007"


def test_status_disposed(disposed):
    cs = disposed["case_status"]
    assert cs["status"] == "Case disposed"
    assert cs["nature_of_disposal"] == "Uncontested--DECREED"


def test_parties_and_advocates(disposed, pending):
    assert disposed["petitioners"] == [{"name": "Punjab National Bank", "advocates": ["DINANATH THAKUR"], "details": None}]
    assert disposed["respondents"][0]["name"] == "Sunil Kumar"
    # Two respondents squeezed into one <li> with <br> separators
    assert [p["name"] for p in pending["respondents"]] == ["MOHINDER PAL SINGH ETC (2)", "JASWINDER SINGH"]


def test_history_and_orders(disposed):
    assert len(disposed["hearing_history"]) >= 10
    first = disposed["hearing_history"][0]
    assert first["purpose_of_hearing"] == "Disposed"
    assert len(first["_business_args"]) == 11
    finals = disposed["final_orders"]
    assert finals[-1]["order_details"] == "COPY OF JUDGMENT"
    assert len(finals[-1]["_pdf_args"]) == 5


def test_malformed_process_table(disposed):
    # The <td>s sit directly in <thead> with no <tr>, so the fallback chunking must handle it.
    assert disposed["processes"][0]["process_id"] == "PDLST010047302024_1_1"


def test_fir_and_transfers(pending):
    assert pending["fir_details"] == {"police_station": "Chanakaya Puri", "fir_number": "10", "year": "2007"}
    assert pending["case_transfers"][0]["transfer_date"] == "01-11-2017"


def test_context_link(disposed):
    ctx = disposed["_context"]
    assert ctx["cino"] == "DLST010047302024" and ctx["state_code"] == "26" and ctx["court_complex_code"] == "1260011"


def test_case_list_vs_br_quirk():
    matches = parse_case_list(load("case_no_result.json", "case_data"))
    assert len(matches) == 1
    m = matches[0]
    assert m["title"] == "Punjab National Bank vs Sunil Kumar"  # `Vs</br>` handled
    assert m["cnr"] == "DLST010047302024"
    assert m["establishment"] == "District and Sessions Judge, South , Saket"


def test_parse_js_call():
    assert parse_js_call("displayPdf('a+b/c==','x','','y')") == ("displayPdf", ["a+b/c==", "x", "", "y"])
    assert parse_js_call(None) is None
