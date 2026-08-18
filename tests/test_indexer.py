from datetime import date
from pathlib import Path

import pytest

from schemelogic.retrieval.indexer import LocalIndex, parse_corpus_file

_SAMPLE_CORPUS_FILE = """doc_id: TEST_DOC
scheme_id: TEST-SCHEME
effective_date: 2024-07-03
citation: Test GR, 3 July 2024
source_type: primary
supersedes_doc_id: TEST_DOC
supersedes_effective_date: 2024-06-28

This is the first paragraph, long enough to survive the 20-char minimum filter.

This is the second paragraph, also long enough to survive the filter.

x
"""


def test_parse_corpus_file_reads_header_fields(tmp_path):
    p = tmp_path / "test.txt"
    p.write_text(_SAMPLE_CORPUS_FILE, encoding="utf-8")
    chunks = parse_corpus_file(p)
    assert all(c.doc_id == "TEST_DOC" for c in chunks)
    assert all(c.scheme_id == "TEST-SCHEME" for c in chunks)
    assert all(c.effective_date == date(2024, 7, 3) for c in chunks)
    assert all(c.citation == "Test GR, 3 July 2024" for c in chunks)
    assert all(c.supersedes_doc_id == "TEST_DOC" for c in chunks)
    assert all(c.supersedes_effective_date == date(2024, 6, 28) for c in chunks)


def test_parse_corpus_file_chunks_by_paragraph_and_drops_short(tmp_path):
    p = tmp_path / "test.txt"
    p.write_text(_SAMPLE_CORPUS_FILE, encoding="utf-8")
    chunks = parse_corpus_file(p)
    # 2 real paragraphs + the "x" line dropped for being under 20 chars
    assert len(chunks) == 2
    assert "first paragraph" in chunks[0].text
    assert "second paragraph" in chunks[1].text


def test_parse_corpus_file_defaults_when_header_sparse(tmp_path):
    p = tmp_path / "minimal.txt"
    p.write_text("doc_id: D\n\nJust one paragraph here, long enough to keep.\n", encoding="utf-8")
    chunks = parse_corpus_file(p)
    assert len(chunks) == 1
    assert chunks[0].effective_date is None
    assert chunks[0].source_type == "primary"
    assert chunks[0].supersedes_doc_id is None


@pytest.fixture(scope="module")
def index():
    idx = LocalIndex()
    from schemelogic.retrieval.indexer import DocumentChunk

    idx.add_chunks(
        [
            DocumentChunk(
                doc_id="D1", scheme_id="S", effective_date=None, citation="c",
                source_path="p", chunk_index=0,
                text="Households whose family members jointly hold more than five acres of "
                     "agricultural land are disqualified from the scheme.",
            ),
            DocumentChunk(
                doc_id="D2", scheme_id="S", effective_date=None, citation="c",
                source_path="p", chunk_index=0,
                text="Applicants must submit a passport-size photograph and proof of residence "
                     "along with the application form.",
            ),
        ]
    )
    return idx


def test_local_index_query_returns_most_relevant_first(index):
    results = index.query("farmland acreage disqualification exclusion", top_k=2)
    assert len(results) == 2
    top_chunk, top_score = results[0]
    assert top_chunk.doc_id == "D1"
    assert top_score > results[1][1]


def test_local_index_len(index):
    assert len(index) == 2


def test_empty_index_query_returns_empty():
    idx = LocalIndex()
    assert idx.query("anything") == []
