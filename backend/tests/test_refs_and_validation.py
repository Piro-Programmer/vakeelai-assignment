import pytest

from app.scraper import refs, service
from app.scraper.errors import InvalidInput


def test_ref_roundtrip_and_tamper():
    tok = refs.encode("pdf", {"a": ["x", "y"]})
    assert refs.decode(tok, "pdf") == {"a": ["x", "y"]}
    body, sig = tok.split(".")
    with pytest.raises(InvalidInput):
        refs.decode(body + "." + sig[::-1], "pdf")  # bad signature
    with pytest.raises(InvalidInput):
        refs.decode(tok, "biz")  # wrong kind


@pytest.mark.parametrize("cnr", ["", "ABC", "DLND02000060200!", "DLND0200006020071"])
def test_cnr_rejected_before_network(cnr):
    with pytest.raises(InvalidInput):
        service.search_cnr(cnr)


def test_case_number_validation():
    args = dict(state_code="26", dist_code="10", court_complex="1260011@1,2,3,4@Y", est_code="1",
                case_type="77^1", case_number="233", year="2024")
    with pytest.raises(InvalidInput):
        service.search_case_number(**{**args, "est_code": ""})  # complex requires establishment
    with pytest.raises(InvalidInput):
        service.search_case_number(**{**args, "est_code": "9"})  # est not in complex
    with pytest.raises(InvalidInput):
        service.search_case_number(**{**args, "year": "2999"})
    with pytest.raises(InvalidInput):
        service.search_case_number(**{**args, "case_number": "12a"})


def test_split_complex():
    assert service._split_complex("1260011@1,2,3,4@Y") == ("1260011", ["1", "2", "3", "4"], True)
    assert service._split_complex("1260002@3@N") == ("1260002", ["3"], False)
