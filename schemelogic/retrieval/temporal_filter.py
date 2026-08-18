"""Temporal filtering (Phase 4, Step 2, plan Section 6.4/8).

A retrieval index returning the highest-similarity chunk isn't enough for amendment documents:
MH-LADKI-BAHIN alone has three dated versions of the same underlying GR lineage (28 June / 3 July
/ 12 July 2024), each amending the last. A query about the farmland-acreage disqualification
should surface the 28 June text if asked "what was the rule as of 1 July 2024" (before the 3 July
amendment took effect) and the 3 July text (which removes it) if asked as of any date from 3 July
onward — never a version that hadn't taken effect yet, and never silently defaulting to
"whichever version is most similar" when that version doesn't apply to the date being asked about.
"""

from __future__ import annotations

from datetime import date

from schemelogic.retrieval.indexer import DocumentChunk

ScoredChunk = tuple[DocumentChunk, float]


def filter_as_of(chunks: list[ScoredChunk], as_of_date: date) -> list[ScoredChunk]:
    """Drops any chunk whose effective_date is strictly after as_of_date. A chunk with no
    effective_date (undated background material) is never dropped by this filter — it's neither
    provably applicable nor provably inapplicable, so exclude it via other means if that
    distinction matters for a given use, not by silently guessing here."""
    return [(c, score) for c, score in chunks if c.effective_date is None or c.effective_date <= as_of_date]


def select_applicable_version(chunks: list[ScoredChunk], as_of_date: date) -> list[ScoredChunk]:
    """Among chunks sharing the same doc_id (multiple dated versions of one document lineage,
    linked via supersedes_doc_id/supersedes_effective_date), keeps only the chunks belonging to
    the LATEST effective_date that is still <= as_of_date for that doc_id — i.e. "the version of
    this document that was actually in force on the date being asked about", not the globally
    most recent version and not every version at once. Chunks from a doc_id with no version dated
    on-or-before as_of_date are dropped entirely for that doc_id (the document lineage didn't
    exist yet as of that date). Chunks with distinct doc_ids are unaffected by each other — this
    only resolves version selection WITHIN one doc_id's lineage."""
    valid = filter_as_of(chunks, as_of_date)

    latest_effective_date_per_doc: dict[str, date] = {}
    for c, _score in valid:
        if c.effective_date is None:
            continue
        current = latest_effective_date_per_doc.get(c.doc_id)
        if current is None or c.effective_date > current:
            latest_effective_date_per_doc[c.doc_id] = c.effective_date

    result = []
    for c, score in valid:
        if c.effective_date is None:
            result.append((c, score))
            continue
        if c.effective_date == latest_effective_date_per_doc.get(c.doc_id):
            result.append((c, score))
    return result
