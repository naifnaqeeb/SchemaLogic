"""extract_scheme() mocked throughout -- no network, no quota touched. Disk cache uses a tmp_path
fixture so tests never touch the real data/cache/ai_checked/ directory."""

import json
from unittest.mock import patch

import pytest

from schemelogic.conversational import ai_checked
from schemelogic.extraction.extractor import ExtractionFailure
from schemelogic.schema.models import Scheme
from tests.fixtures import PM_KISAN


def make_pm_kisan_scheme() -> Scheme:
    """Stand-in Scheme for these tests -- any validated Scheme instance works, since ai_checked.py
    never inspects its contents, only ever passes it through."""
    return Scheme.model_validate(PM_KISAN)


@pytest.fixture(autouse=True)
def _tmp_disk_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_checked, "DISK_CACHE_DIR", tmp_path / "ai_checked_cache")


VACUOUS_SCHEME = {
    "scheme_id": "VACUOUS",
    "unit_of_eligibility": "individual",
    # Exactly the shape a real 3,938-char myScheme document collapsed to on 2026-09-15, while
    # self-reporting confidence 0.95 / flagged_for_review False.
    "inclusion": {"and": [{"cat": "citizenship", "field": "is_indian_citizen", "op": "==", "value": True}]},
    "exclusions": [],
    "temporal_validity": {"valid_from": "2020-01-01", "extracted_at": "2026-01-01"},
    "extraction_metadata": {"confidence": 0.95, "source_clause": "x", "flagged_for_review": False},
}

ONE_REAL_CRITERION_SCHEME = {
    "scheme_id": "THIN-BUT-REAL",
    "unit_of_eligibility": "individual",
    "inclusion": {
        "and": [
            {"cat": "citizenship", "field": "is_indian_citizen", "op": "==", "value": True},
            {"cat": "demographic", "field": "is_woman", "op": "==", "value": True},
        ]
    },
    "exclusions": [],
    "temporal_validity": {"valid_from": "2020-01-01", "extracted_at": "2026-01-01"},
    "extraction_metadata": {"confidence": 0.4, "source_clause": "x", "flagged_for_review": True},
}


def test_is_vacuous_flags_a_rule_free_extraction():
    assert ai_checked.is_vacuous(Scheme.model_validate(VACUOUS_SCHEME)) is True


def test_is_vacuous_does_not_flag_a_genuine_single_criterion_scheme():
    """The guard must catch collapsed extractions without rejecting real one-criterion schemes --
    'Indian citizen AND woman' discriminates between citizens; 'Indian citizen' alone does not."""
    assert ai_checked.is_vacuous(Scheme.model_validate(ONE_REAL_CRITERION_SCHEME)) is False


def test_is_vacuous_does_not_flag_a_scheme_carrying_only_exclusions():
    scheme = Scheme.model_validate(
        {**VACUOUS_SCHEME, "exclusions": [
            {"cat": "economic", "quantifier": "self", "field": "paid_income_tax_last_assessment_year",
             "op": "==", "value": True},
        ]}
    )
    assert ai_checked.is_vacuous(scheme) is False


def test_vacuous_extraction_falls_back_to_description_only_and_is_not_disk_cached():
    """Honest-failure requirement: a schema-valid but rule-free extraction must be treated exactly
    like a failure, so the citizen gets the description rather than a meaningless one-question Q&A
    ending in a confident-looking verdict."""
    record = {"scheme_name": "Big Scheme", "description": "lots of prose", "eligibility_text": "lots more"}
    session_cache: dict = {}
    with patch(
        "schemelogic.conversational.ai_checked.extract_scheme",
        return_value=Scheme.model_validate(VACUOUS_SCHEME),
    ):
        result = ai_checked.get_or_extract_scheme("vac-slug", record, session_cache)
    assert result is None
    assert session_cache["vac-slug"] is None
    assert not (ai_checked.DISK_CACHE_DIR / "vac-slug.json").exists()


def test_transient_failure_is_not_session_cached_so_reselecting_retries():
    """A 429 says the account was busy, not that the scheme is un-extractable. Caching it as a
    permanent failure pinned that scheme to description-only for the whole session -- the dominant
    real-world cause of the fallback per the 2026-09-15 diagnosis (one extraction costs ~7.5k
    tokens against a flat 8000 TPM ceiling, so a 429 mid-chat is routine)."""
    record = {"scheme_name": "S", "description": "d", "eligibility_text": "e"}
    session_cache: dict = {}
    scheme = make_pm_kisan_scheme()
    with patch(
        "schemelogic.conversational.ai_checked.extract_scheme",
        side_effect=[ExtractionFailure(reason="rate_limited", detail="429"), scheme],
    ) as mock_extract:
        first, failure = ai_checked.extract_with_reason("slug-429", record, session_cache)
        assert first is None
        assert failure is not None and failure.reason == "rate_limited"
        assert "slug-429" not in session_cache  # NOT remembered as a failure

        second, failure2 = ai_checked.extract_with_reason("slug-429", record, session_cache)
    assert second is scheme  # the retry really happens and can succeed
    assert failure2 is None
    assert mock_extract.call_count == 2


def test_content_shaped_failure_is_session_cached_and_not_retried():
    """The counterpart: re-submitting the same text to the same model gives the same result, so a
    content-shaped failure IS remembered -- that's the quota discipline the tier depends on."""
    record = {"scheme_name": "S", "description": "d", "eligibility_text": "e"}
    session_cache: dict = {}
    with patch(
        "schemelogic.conversational.ai_checked.extract_scheme",
        return_value=ExtractionFailure(reason="schema_validation_failed", detail="bad"),
    ) as mock_extract:
        ai_checked.extract_with_reason("slug-bad", record, session_cache)
        ai_checked.extract_with_reason("slug-bad", record, session_cache)
    assert session_cache["slug-bad"] is None
    assert mock_extract.call_count == 1


def test_get_or_extract_scheme_still_returns_a_bare_scheme_or_none():
    """The original signature is what chat_engine's tests and the API layer use -- kept as a thin
    wrapper so adding the failure reason didn't become a breaking change."""
    record = {"scheme_name": "S", "description": "d", "eligibility_text": "e"}
    scheme = make_pm_kisan_scheme()
    with patch("schemelogic.conversational.ai_checked.extract_scheme", return_value=scheme):
        assert ai_checked.get_or_extract_scheme("s1", record, {}) is scheme
    with patch(
        "schemelogic.conversational.ai_checked.extract_scheme",
        return_value=ExtractionFailure(reason="malformed_json", detail="x"),
    ):
        assert ai_checked.get_or_extract_scheme("s2", record, {}) is None


def test_build_source_text_concatenates_available_fields():
    record = {"scheme_name": "Test Scheme", "description": "desc here", "eligibility_text": "elig here"}
    text = ai_checked.build_source_text(record)
    assert "Test Scheme" in text and "desc here" in text and "elig here" in text


def test_build_source_text_skips_missing_fields():
    record = {"scheme_name": "Test Scheme", "description": None, "eligibility_text": ""}
    text = ai_checked.build_source_text(record)
    assert text.strip() == "Test Scheme"


def test_empty_source_text_short_circuits_without_calling_llm():
    record = {"scheme_name": "", "description": None, "eligibility_text": None}
    with patch("schemelogic.conversational.ai_checked.extract_scheme") as mock_extract:
        result = ai_checked.get_or_extract_scheme("slug1", record, session_cache={})
    mock_extract.assert_not_called()
    assert result is None


def test_successful_extraction_cached_in_session_and_disk():
    scheme = make_pm_kisan_scheme()
    record = {"scheme_name": "Test Scheme", "description": "desc", "eligibility_text": "elig"}
    session_cache: dict = {}
    with patch("schemelogic.conversational.ai_checked.extract_scheme", return_value=scheme):
        result = ai_checked.get_or_extract_scheme("test-slug", record, session_cache)
    assert result is scheme
    assert session_cache["test-slug"] is scheme
    assert ai_checked._disk_cache_path("test-slug").exists()


def test_session_cache_hit_never_calls_llm_again():
    scheme = make_pm_kisan_scheme()
    session_cache = {"test-slug": scheme}
    with patch("schemelogic.conversational.ai_checked.extract_scheme") as mock_extract:
        result = ai_checked.get_or_extract_scheme("test-slug", {}, session_cache)
    mock_extract.assert_not_called()
    assert result is scheme


def test_session_cache_hit_on_prior_failure_never_retries():
    session_cache = {"test-slug": None}
    with patch("schemelogic.conversational.ai_checked.extract_scheme") as mock_extract:
        result = ai_checked.get_or_extract_scheme("test-slug", {"description": "x"}, session_cache)
    mock_extract.assert_not_called()
    assert result is None


def test_extraction_failure_returns_none_not_exception():
    record = {"scheme_name": "Test Scheme", "description": "desc", "eligibility_text": "elig"}
    session_cache: dict = {}
    with patch(
        "schemelogic.conversational.ai_checked.extract_scheme",
        return_value=ExtractionFailure(reason="schema_validation_failed", detail="bad"),
    ):
        result = ai_checked.get_or_extract_scheme("test-slug", record, session_cache)
    assert result is None
    assert session_cache["test-slug"] is None
    assert not ai_checked._disk_cache_path("test-slug").exists()  # failures never hit disk


def test_unexpected_exception_degrades_to_none_not_a_crash():
    record = {"scheme_name": "Test Scheme", "description": "desc", "eligibility_text": "elig"}
    session_cache: dict = {}
    with patch("schemelogic.conversational.ai_checked.extract_scheme", side_effect=RuntimeError("boom")):
        result = ai_checked.get_or_extract_scheme("test-slug", record, session_cache)
    assert result is None
    assert session_cache["test-slug"] is None


def test_disk_cache_hit_populates_session_cache_without_calling_llm():
    scheme = make_pm_kisan_scheme()
    record = {"scheme_name": "Test Scheme", "description": "desc", "eligibility_text": "elig"}
    with patch("schemelogic.conversational.ai_checked.extract_scheme", return_value=scheme):
        ai_checked.get_or_extract_scheme("disk-slug", record, session_cache={})  # populate disk

    fresh_session_cache: dict = {}
    with patch("schemelogic.conversational.ai_checked.extract_scheme") as mock_extract:
        result = ai_checked.get_or_extract_scheme("disk-slug", record, fresh_session_cache)
    mock_extract.assert_not_called()
    assert result == scheme
    assert fresh_session_cache["disk-slug"] == scheme


def test_corrupt_disk_cache_entry_degrades_gracefully():
    path = ai_checked._disk_cache_path("bad-slug")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not valid json {{{", encoding="utf-8")
    scheme = make_pm_kisan_scheme()
    record = {"scheme_name": "Test Scheme", "description": "desc", "eligibility_text": "elig"}
    with patch("schemelogic.conversational.ai_checked.extract_scheme", return_value=scheme):
        result = ai_checked.get_or_extract_scheme("bad-slug", record, session_cache={})
    assert result == scheme



def test_cached_scheme_with_applicant_scope_is_refused():
    """Extraction can only produce member scope (extractor._without_except_scope), so a cached
    AI-Checked scheme carrying applicant scope wasn't produced by this pipeline -- refuse it."""
    data = dict(PM_KISAN)
    data["exclusions"] = [dict(e) for e in PM_KISAN["exclusions"]]
    data["exclusions"][1]["except_scope"] = "applicant"  # some_family_member, has an except
    ai_checked.DISK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (ai_checked.DISK_CACHE_DIR / "tampered.json").write_text(json.dumps(data), encoding="utf-8")
    assert ai_checked._load_from_disk("tampered") is None
