"""extract_scheme() mocked throughout -- no network, no quota touched. Disk cache uses a tmp_path
fixture so tests never touch the real data/cache/ai_checked/ directory."""

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
