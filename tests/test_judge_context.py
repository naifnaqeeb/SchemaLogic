from datetime import date

import pytest

from schemelogic.retrieval.indexer import DocumentChunk, LocalIndex
from schemelogic.retrieval.judge_context import retrieve_context_for_judge


@pytest.fixture(scope="module")
def index():
    idx = LocalIndex()
    idx.add_chunks(
        [
            DocumentChunk(
                doc_id="D", scheme_id="S", effective_date=date(2024, 6, 28), citation="original GR",
                source_path="p", chunk_index=0,
                text="Households whose family members jointly hold more than five acres of "
                     "agricultural land are disqualified.",
            ),
            DocumentChunk(
                doc_id="D", scheme_id="S", effective_date=date(2024, 7, 3), citation="amendment GR",
                source_path="p", chunk_index=0,
                text="The farmland disqualification condition is hereby removed.",
                supersedes_doc_id="D", supersedes_effective_date=date(2024, 6, 28),
            ),
        ]
    )
    return idx


def test_returns_applicable_version_only(index):
    context = retrieve_context_for_judge(index, "farmland disqualification", date(2024, 8, 1))
    assert "hereby removed" in context
    assert "five acres" not in context


def test_returns_earlier_version_for_earlier_as_of_date(index):
    context = retrieve_context_for_judge(index, "farmland disqualification", date(2024, 7, 1))
    assert "five acres" in context
    assert "hereby removed" not in context


def test_empty_string_when_nothing_applicable(index):
    context = retrieve_context_for_judge(index, "farmland disqualification", date(2020, 1, 1))
    assert context == ""


def test_includes_citation_and_date_metadata(index):
    context = retrieve_context_for_judge(index, "farmland disqualification", date(2024, 8, 1))
    assert "amendment GR" in context
    assert "2024-07-03" in context
