"""Local retrieval index (Phase 4, Step 1, plan Section 6.4/8).

Embedding/indexing/retrieval is entirely local — no Groq (or any other external API) call
anywhere in this module. `sentence-transformers` (all-MiniLM-L6-v2, ~80MB, CPU-friendly) runs
inference on-device; the only network activity is the one-time model weight download on first
use, cached afterward by huggingface_hub. This matters because this account's Groq daily token
cap was already hit once this session — indexing hundreds of amendment/notification documents
must never compete with that budget.

Corpus documents live as plain `.txt` files in a directory (see `data/retrieval_corpus/` — seeded
with the real amendment source documents already on hand from gold annotation: the three
MH-LADKI-BAHIN GR PDFs (28 June / 3 July / 12 July 2024, read via the Read tool and transcribed
verbatim in Marathi — the original, not a translation) and a PM-KISAN amendment reference (marked
`source_type: secondary` — no primary Cabinet decision document was ever located for PM-KISAN, per
this project's own gold-annotation record; the corpus is explicit about this rather than
pretending otherwise). Each file: a small `key: value` metadata header, a blank line, then body
text chunked by paragraph (blank-line-separated) — these are short GR/notification texts, not
long documents needing token-window chunking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass(frozen=True)
class DocumentChunk:
    doc_id: str
    scheme_id: str
    effective_date: date | None
    citation: str
    source_path: str
    chunk_index: int
    text: str
    source_type: str = "primary"  # "primary" | "secondary" -- see PM-KISAN's corpus file for why
    supersedes_doc_id: str | None = None
    supersedes_effective_date: date | None = None


def _parse_header(header_text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in header_text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def parse_corpus_file(path: Path) -> list[DocumentChunk]:
    """Header (key: value lines) + blank line + body, body chunked by blank-line-separated
    paragraphs. A paragraph shorter than 20 chars (stray whitespace, a lone label) is dropped."""
    raw = path.read_text(encoding="utf-8")
    header_text, _, body = raw.partition("\n\n")
    fields = _parse_header(header_text)

    doc_id = fields.get("doc_id", path.stem)
    scheme_id = fields.get("scheme_id", "")
    effective_date = _parse_date(fields.get("effective_date"))
    citation = fields.get("citation", "")
    source_type = fields.get("source_type", "primary")
    supersedes_doc_id = fields.get("supersedes_doc_id") or None
    supersedes_effective_date = _parse_date(fields.get("supersedes_effective_date"))

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if len(p.strip()) >= 20]
    return [
        DocumentChunk(
            doc_id=doc_id,
            scheme_id=scheme_id,
            effective_date=effective_date,
            citation=citation,
            source_path=str(path),
            chunk_index=i,
            text=p,
            source_type=source_type,
            supersedes_doc_id=supersedes_doc_id,
            supersedes_effective_date=supersedes_effective_date,
        )
        for i, p in enumerate(paragraphs)
    ]


class LocalIndex:
    """In-memory cosine-similarity index over locally-computed embeddings. No persistence layer —
    the corpus is small enough (a handful of documents for this validation pass) that rebuilding
    from `data/retrieval_corpus/` on every process start is cheap and avoids a stale-index class
    of bugs entirely; add a persistence layer only if/when the corpus grows enough to make
    re-embedding on every run actually slow."""

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL):
        self._model = SentenceTransformer(model_name)
        self._chunks: list[DocumentChunk] = []
        self._embeddings: np.ndarray | None = None

    def add_chunks(self, chunks: list[DocumentChunk]) -> None:
        if not chunks:
            return
        new_embeddings = self._model.encode([c.text for c in chunks], normalize_embeddings=True)
        self._chunks.extend(chunks)
        self._embeddings = (
            new_embeddings
            if self._embeddings is None
            else np.vstack([self._embeddings, new_embeddings])
        )

    def __len__(self) -> int:
        return len(self._chunks)

    def query(self, text: str, top_k: int = 5) -> list[tuple[DocumentChunk, float]]:
        """Cosine similarity (embeddings are pre-normalized, so this is a plain dot product) —
        purely local, no network/API call."""
        if not self._chunks:
            return []
        query_embedding = self._model.encode([text], normalize_embeddings=True)[0]
        scores = self._embeddings @ query_embedding
        top_indices = np.argsort(-scores)[:top_k]
        return [(self._chunks[i], float(scores[i])) for i in top_indices]


def build_index_from_directory(
    corpus_dir: Path, model_name: str = DEFAULT_EMBEDDING_MODEL
) -> LocalIndex:
    index = LocalIndex(model_name=model_name)
    for path in sorted(corpus_dir.glob("*.txt")):
        index.add_chunks(parse_corpus_file(path))
    return index
