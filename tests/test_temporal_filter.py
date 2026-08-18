from datetime import date

from schemelogic.retrieval.indexer import DocumentChunk
from schemelogic.retrieval.temporal_filter import filter_as_of, select_applicable_version


def _chunk(doc_id, effective_date, text="t", **kw):
    return DocumentChunk(
        doc_id=doc_id, scheme_id="TEST", effective_date=effective_date, citation="c",
        source_path="p", chunk_index=0, text=text, **kw,
    )


def test_filter_as_of_drops_future_chunks():
    chunks = [
        (_chunk("D", date(2024, 6, 28)), 0.9),
        (_chunk("D", date(2024, 7, 3)), 0.8),
        (_chunk("D", date(2024, 7, 12)), 0.7),
    ]
    result = filter_as_of(chunks, date(2024, 7, 1))
    dates = sorted(c.effective_date for c, _ in result)
    assert dates == [date(2024, 6, 28)]


def test_filter_as_of_keeps_undated_chunks():
    chunks = [(_chunk("D", None), 0.5)]
    result = filter_as_of(chunks, date(2024, 1, 1))
    assert len(result) == 1


def test_select_applicable_version_picks_latest_before_as_of():
    """The exact MH-LADKI-BAHIN shape: 3 dated versions of the same doc_id lineage."""
    chunks = [
        (_chunk("MH-LADKI-BAHIN_GR", date(2024, 6, 28), text="original: >5 acres disqualifies"), 0.9),
        (_chunk("MH-LADKI-BAHIN_GR", date(2024, 7, 3), text="amendment: >5 acres removed"), 0.85),
        (_chunk("MH-LADKI-BAHIN_GR", date(2024, 7, 12), text="family definition clarified"), 0.8),
    ]
    # As of a date between the original and the amendment -- must get the ORIGINAL, not the
    # amendment (which hadn't taken effect yet) and not the most-similar-scoring chunk blindly.
    result = select_applicable_version(chunks, date(2024, 7, 1))
    assert len(result) == 1
    assert "original" in result[0][0].text

    # As of a date after the amendment but before the 3rd version -- must get the amendment.
    result = select_applicable_version(chunks, date(2024, 7, 10))
    assert len(result) == 1
    assert "amendment" in result[0][0].text

    # As of a date after all three -- must get the latest.
    result = select_applicable_version(chunks, date(2024, 8, 1))
    assert len(result) == 1
    assert "family definition" in result[0][0].text


def test_select_applicable_version_no_version_exists_yet():
    chunks = [(_chunk("D", date(2024, 6, 28), text="x"), 0.9)]
    result = select_applicable_version(chunks, date(2024, 1, 1))
    assert result == []


def test_select_applicable_version_distinct_doc_ids_independent():
    chunks = [
        (_chunk("A", date(2024, 1, 1), text="a"), 0.9),
        (_chunk("B", date(2024, 1, 1), text="b"), 0.8),
    ]
    result = select_applicable_version(chunks, date(2024, 6, 1))
    assert {c.doc_id for c, _ in result} == {"A", "B"}


def test_select_applicable_version_keeps_undated_chunks():
    chunks = [(_chunk("D", None, text="background"), 0.5)]
    result = select_applicable_version(chunks, date(2024, 1, 1))
    assert len(result) == 1
