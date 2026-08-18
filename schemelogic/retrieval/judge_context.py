"""Composes indexer.query() + temporal_filter.select_applicable_version() into judge-ready
context text (Phase 4, Step 3's integration point). Kept separate from judge_repair.py so the
judge module doesn't need to import retrieval internals directly — it only ever sees a formatted
string, same as any other piece of prompt text.
"""

from __future__ import annotations

from datetime import date

from schemelogic.retrieval.indexer import LocalIndex
from schemelogic.retrieval.temporal_filter import select_applicable_version

DEFAULT_TOP_K = 8
"""Generous default, not the more typical 3-5: cross-lingual retrieval (an English query against
Marathi-language source chunks, e.g.) was observed to compress similarity scores enough that a
genuinely relevant chunk can rank outside a narrow top-5 even though it's clearly the right
document — see retrieval/indexer.py's module docstring / this project's Phase 4 validation report
for the concrete example (MH-LADKI-BAHIN's farmland-exclusion amendment chunk)."""


def retrieve_context_for_judge(
    index: LocalIndex,
    query: str,
    as_of_date: date,
    top_k: int = DEFAULT_TOP_K,
) -> str:
    """Returns "" (not None) when nothing survives temporal filtering — judge_repair.run_judge()
    treats a falsy retrieved_context as "no context available", same as never having called this
    at all, so an empty result here is a safe, unambiguous no-op for the caller."""
    results = index.query(query, top_k=top_k)
    applicable = select_applicable_version(results, as_of_date)
    if not applicable:
        return ""

    parts = []
    for chunk, score in applicable:
        parts.append(
            f"[{chunk.doc_id} — {chunk.citation} — effective {chunk.effective_date} — "
            f"source_type: {chunk.source_type} — similarity {score:.3f}]\n{chunk.text}"
        )
    return "\n\n".join(parts)
