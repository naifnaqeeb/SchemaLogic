from pathlib import Path

import pytest

from schemelogic.discovery.indexer import (
    GOLD_SCHEME_NAMES,
    DescriptionMatch,
    next_steps_for_silver,
    resolve_gold_description,
    resolve_next_steps,
    search,
)
from schemelogic.retrieval.indexer import DocumentChunk, LocalIndex

RAW_DOCS_DIR = Path("data/raw_documents")


def test_exact_match_preferred_over_fuzzy():
    silver = [
        {"slug": "pm-kisan", "scheme_name": "Pradhan Mantri Kisan Samman Nidhi", "description": "exact match desc"},
        {"slug": "pmk-2", "scheme_name": "Pradhan Mantri Kisan Yojana Extra", "description": "fuzzy match desc"},
    ]
    m = resolve_gold_description("PM-KISAN", silver, RAW_DOCS_DIR)
    assert m.match_type == "silver_exact"
    assert m.matched_silver_slug == "pm-kisan"
    assert m.description == "exact match desc"


def test_fuzzy_match_deprioritizes_state_suffixed_candidate():
    """The real bug found while building this: a state-suffixed variant tied on extra-token
    count with a plain-prefixed one and won by iteration order. Must not regress."""
    silver = [
        {"slug": "ignoaps-sikkim", "scheme_name": "Indira Gandhi National Old Age Pension Scheme - Sikkim", "description": "sikkim desc"},
        {"slug": "nsap-ignoaps", "scheme_name": "NSAP - Indira Gandhi National Old Age Pension Scheme", "description": "central desc"},
    ]
    m = resolve_gold_description("IGNOAPS", silver, RAW_DOCS_DIR)
    assert m.match_type == "silver_fuzzy"
    assert m.matched_silver_slug == "nsap-ignoaps"
    assert m.description == "central desc"


def test_low_overlap_candidate_rejected_not_fuzzy_matched():
    """The other real bug found: a low-overlap, wrong-scheme candidate (different real-world
    scheme entirely) must not be accepted just because it's the best of a bad lot."""
    silver = [
        {"slug": "pmjdy", "scheme_name": "Pradhan Mantri Jan Dhan Yojana", "description": "wrong scheme"},
    ]
    m = resolve_gold_description("AB-PMJAY", silver, RAW_DOCS_DIR)
    assert m.match_type != "silver_fuzzy"


def test_no_silver_match_falls_back_to_source_doc_intro():
    m = resolve_gold_description("AB-PMJAY", [], RAW_DOCS_DIR)
    assert m.match_type == "source_doc_fallback"
    assert m.description  # non-empty
    assert m.matched_silver_slug is None


def test_no_match_no_fallback_when_source_doc_missing():
    m = resolve_gold_description("PM-KISAN", [], Path("no/such/dir"))
    assert m.match_type == "no_description"
    assert m.description == ""


def test_unknown_scheme_id_raises():
    with pytest.raises(ValueError):
        resolve_gold_description("NOT-A-REAL-SCHEME", [], RAW_DOCS_DIR)


def test_every_gold_scheme_name_resolves_to_some_description():
    """Real-data smoke test (no embeddings, just the source docs on disk) -- every gold scheme
    must end up with SOME description, never silently empty, given the real raw_documents/ dir."""
    for scheme_id in GOLD_SCHEME_NAMES:
        m = resolve_gold_description(scheme_id, [], RAW_DOCS_DIR)
        assert m.description, f"{scheme_id} got no description at all (match_type={m.match_type})"


# --- resolve_next_steps (Part 3) --------------------------------------------------------------


def test_next_steps_uses_matched_silver_record():
    match = DescriptionMatch(description="d", match_type="silver_exact", matched_silver_slug="pm-kisan")
    silver_by_slug = {
        "pm-kisan": {"benefits_text": "6000/yr", "application_process_text": "apply online", "official_link": "https://x"},
    }
    ns = resolve_next_steps("PM-KISAN", match, silver_by_slug, RAW_DOCS_DIR)
    assert ns.source == "silver"
    assert ns.benefits_text == "6000/yr"
    assert ns.application_process_text == "apply online"
    assert ns.official_link == "https://x"


def test_next_steps_falls_back_to_source_doc_when_no_match():
    """MH-LADKI-BAHIN has a real '## Benefit' section on disk -- must be found by keyword, not
    just the first section."""
    match = DescriptionMatch(description="d", match_type="source_doc_fallback", matched_silver_slug=None)
    ns = resolve_next_steps("MH-LADKI-BAHIN", match, {}, RAW_DOCS_DIR)
    assert ns.source == "source_doc"
    assert ns.benefits_text
    assert ns.official_link is None  # never fabricated -- source docs don't carry a link


def test_next_steps_ab_pmjay_has_no_benefit_heading_but_has_application_proxy():
    """AB-PMJAY's source doc has no '## Benefit' section at all (amount is inline in Objective,
    already used as the description) -- benefits_text should honestly be None, not guessed."""
    match = DescriptionMatch(description="d", match_type="source_doc_fallback", matched_silver_slug=None)
    ns = resolve_next_steps("AB-PMJAY", match, {}, RAW_DOCS_DIR)
    assert ns.benefits_text is None
    assert ns.application_process_text  # "Operational Requirements" proxy


def test_next_steps_no_match_no_source_doc_returns_none_source():
    match = DescriptionMatch(description="", match_type="no_description", matched_silver_slug=None)
    ns = resolve_next_steps("NOT-A-REAL-SCHEME", match, {}, RAW_DOCS_DIR)
    assert ns.source == "none"
    assert ns.benefits_text is None
    assert ns.application_process_text is None


def test_next_steps_for_silver_reads_record_directly():
    record = {"benefits_text": "b", "application_process_text": "a", "official_link": "l"}
    ns = next_steps_for_silver(record)
    assert ns == next_steps_for_silver(record)
    assert ns.source == "silver"
    assert (ns.benefits_text, ns.application_process_text, ns.official_link) == ("b", "a", "l")


# --- search() gold-slot guarantee (small synthetic index, no real 2073-record corpus needed) ---


@pytest.fixture(scope="module")
def synthetic_index():
    index = LocalIndex()
    chunks = [
        DocumentChunk(
            doc_id="GOLD-SCHEME", scheme_id="GOLD-SCHEME", effective_date=None, citation="",
            source_path="", chunk_index=0, text="old age pension scheme for senior citizens",
            source_type="gold",
        ),
    ]
    # Many silver chunks using near-identical wording so they'd normally crowd out the one gold
    # chunk by sheer repetition/count.
    for i in range(30):
        chunks.append(
            DocumentChunk(
                doc_id=f"silver-{i}", scheme_id=f"silver-{i}", effective_date=None, citation="",
                source_path="", chunk_index=0,
                text=f"old age pension scheme state variant number {i} for senior citizens",
                source_type="silver_unverified",
            )
        )
    index.add_chunks(chunks)
    return index


def test_search_guarantees_gold_slot_even_when_outranked(synthetic_index):
    results = search(synthetic_index, "old age pension", top_k=5, min_gold_slots=2)
    assert any(c.source_type == "gold" for c, _ in results)


def test_search_returns_at_most_top_k(synthetic_index):
    results = search(synthetic_index, "old age pension", top_k=5)
    assert len(results) <= 5


def test_search_no_gold_available_returns_only_silver():
    index = LocalIndex()
    index.add_chunks(
        [
            DocumentChunk(
                doc_id="s1", scheme_id="s1", effective_date=None, citation="", source_path="",
                chunk_index=0, text="some silver scheme", source_type="silver_unverified",
            )
        ]
    )
    results = search(index, "some silver scheme", top_k=5)
    assert all(c.source_type == "silver_unverified" for c, _ in results)
