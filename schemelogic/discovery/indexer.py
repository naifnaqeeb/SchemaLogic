"""Discovery layer (readability/discovery build, Part B). Local embeddings only — reuses Phase
4's sentence-transformers setup (schemelogic.retrieval.indexer.LocalIndex/DocumentChunk directly,
not a reimplementation) — zero Groq/OpenRouter cost, same as retrieval.

Purely descriptive metadata layer: matches each gold scheme to a silver-set description (by
scheme name) for discovery-search purposes ONLY. Never touches, reads, or overrides a gold
scheme's actual eligibility logic (Scheme.inclusion/exclusions) — this module only ever looks at
scheme_id strings and free-text descriptions.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from schemelogic.ingestion.silver_scraper import INDIAN_STATES_AND_UTS, clean_record_text, fix_mojibake
from schemelogic.retrieval.indexer import DEFAULT_EMBEDDING_MODEL, DocumentChunk, LocalIndex

# Gold scheme_id -> full scheme name, used only to MATCH against silver scheme_name strings (and
# as the discovery display name for gold results) -- never used to alter eligibility logic.
GOLD_SCHEME_NAMES: dict[str, str] = {
    "AB-PMJAY": "Ayushman Bharat Pradhan Mantri Jan Arogya Yojana",
    "IGNOAPS": "Indira Gandhi National Old Age Pension Scheme",
    "MH-LADKI-BAHIN": "Mukhyamantri Majhi Ladki Bahin Yojana",
    "PM-KISAN": "Pradhan Mantri Kisan Samman Nidhi",
    "PM-UJJWALA-2.0": "Pradhan Mantri Ujjwala Yojana 2.0",
    "PMAY-G": "Pradhan Mantri Awaas Yojana Gramin",
    "PMMVY": "Pradhan Mantri Matru Vandana Yojana",
}

# Empirically-tuned conservative threshold: at 0.85, matching against real silver data correctly
# EXCLUDES two genuine near-misses found while building this -- AB-PMJAY's best silver candidate
# (0.57 token overlap) turned out to be "Pradhan Mantri Jan Dhan Yojana", a completely different
# scheme; MH-LADKI-BAHIN's only "ladki bahin"-ish silver hit is Madhya Pradesh's "Chief Minister
# Ladli Behna Yojana" (cmlby) -- a different state's different scheme with a confusingly similar
# name, not Maharashtra's. Both are exactly the kind of wrong-but-plausible match this project
# has repeatedly favored erring conservative against elsewhere (calibration_gate.py, judge scope).
_FUZZY_MATCH_THRESHOLD = 0.85


def _normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\([^)]*\)", " ", s)  # strip parentheticals
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# Individual lowercase word tokens from every state/UT name (e.g. "sikkim", or "madhya"/"pradesh"
# separately) -- used to deprioritize a fuzzy-matched silver record that's actually a
# state-specific variant of the target central scheme, not the base scheme itself. Found
# necessary empirically: without this, IGNOAPS's fuzzy match picked "ignoaps-sikkim" over the
# plain "nsap-ignoaps" purely because both tied on extra-token COUNT (1 each: "sikkim" vs
# "nsap") -- the state-name check is what actually distinguishes "this is a regional variant"
# from "this is just a differently-prefixed version of the same central scheme."
_STATE_NAME_TOKENS = {tok for name in INDIAN_STATES_AND_UTS for tok in _normalize(name).split()}


@dataclass(frozen=True)
class DescriptionMatch:
    description: str
    match_type: str  # "silver_exact" | "silver_fuzzy" | "source_doc_fallback" | "no_description"
    matched_silver_slug: str | None = None


def _source_doc_sections(scheme_id: str, raw_documents_dir: Path) -> dict[str, str] | None:
    """{heading_text_lowercased: body} for every "## " section in data/raw_documents/{scheme_id}.md.
    None if the doc doesn't exist. Generic — doesn't hardcode which headings a given doc uses,
    since they vary (AB-PMJAY has no "Benefit" section at all; MH-LADKI-BAHIN does)."""
    path = raw_documents_dir / f"{scheme_id}.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^\s*<!--.*?-->\s*", "", text, flags=re.DOTALL)  # strip provenance HTML comment
    sections = re.split(r"\n## ", text)
    result: dict[str, str] = {}
    for section in sections[1:]:  # sections[0] is the "# Title" line + anything before the first "## "
        heading, _, body = section.partition("\n")
        # These docs are hand-curated, not myScheme-PDF-scraped, so mojibake is unlikely here in
        # practice -- fix_mojibake() is a no-op on already-clean text, so applying it anyway costs
        # nothing and keeps this fallback path consistent with every other text source (Bug 3).
        result[heading.strip().lower()] = fix_mojibake(body.strip())
    return result


def _source_doc_intro(scheme_id: str, raw_documents_dir: Path) -> str | None:
    """First section's body — whatever heading comes right after the H1 title, generically."""
    sections = _source_doc_sections(scheme_id, raw_documents_dir)
    if not sections:
        return None
    first_body = next(iter(sections.values()), None)
    return first_body or None


def _find_section(sections: dict[str, str], *keywords: str) -> str | None:
    for heading, body in sections.items():
        if any(kw in heading for kw in keywords) and body:
            return body
    return None


@dataclass(frozen=True)
class NextSteps:
    benefits_text: str | None
    application_process_text: str | None
    official_link: str | None
    source: str  # "silver" | "source_doc" | "none"


def resolve_next_steps(
    scheme_id: str,
    match: DescriptionMatch,
    silver_by_slug: dict[str, dict],
    raw_documents_dir: Path,
) -> NextSteps:
    """Reuses the SAME match already computed by resolve_gold_description (via `match`) rather
    than re-running fuzzy matching a second time — one match per gold scheme, used for both its
    description (Part B) and its next-step info (Part 3)."""
    if match.matched_silver_slug is not None:
        record = silver_by_slug.get(match.matched_silver_slug)
        if record is not None:
            return next_steps_for_silver(record)

    sections = _source_doc_sections(scheme_id, raw_documents_dir)
    if sections:
        benefits = _find_section(sections, "benefit")
        application = _find_section(sections, "application", "documents required", "how to apply", "operational")
        if benefits or application:
            return NextSteps(benefits_text=benefits, application_process_text=application, official_link=None, source="source_doc")

    return NextSteps(benefits_text=None, application_process_text=None, official_link=None, source="none")


def next_steps_for_silver(record: dict) -> NextSteps:
    """Silver schemes never need the gold-matching dance — their own record already has
    everything."""
    return NextSteps(
        benefits_text=record.get("benefits_text"),
        application_process_text=record.get("application_process_text"),
        official_link=record.get("official_link"),
        source="silver",
    )


def resolve_gold_description(scheme_id: str, silver_records: list[dict], raw_documents_dir: Path) -> DescriptionMatch:
    name = GOLD_SCHEME_NAMES.get(scheme_id)
    if name is None:
        raise ValueError(f"no known display name for gold scheme_id {scheme_id!r} -- add it to GOLD_SCHEME_NAMES")

    target_norm = _normalize(name)
    target_tokens = set(target_norm.split())

    by_norm_name = {}
    for r in silver_records:
        if r.get("scheme_name"):
            by_norm_name.setdefault(_normalize(r["scheme_name"]), r)

    exact = by_norm_name.get(target_norm)
    if exact is not None and exact.get("description"):
        return DescriptionMatch(description=exact["description"], match_type="silver_exact", matched_silver_slug=exact["slug"])

    best_key: tuple[float, int, int] | None = None  # (overlap, -has_state_token, -extra_token_count)
    best_record: dict | None = None
    for r in silver_records:
        if not r.get("scheme_name") or not r.get("description"):
            continue
        candidate_tokens = set(_normalize(r["scheme_name"]).split())
        if not candidate_tokens:
            continue
        overlap = len(target_tokens & candidate_tokens) / len(target_tokens)
        if overlap < _FUZZY_MATCH_THRESHOLD:
            continue
        extra_tokens = candidate_tokens - target_tokens
        has_state_token = bool(extra_tokens & _STATE_NAME_TOKENS)
        key = (overlap, -1 if has_state_token else 0, -len(extra_tokens))
        if best_key is None or key > best_key:
            best_key, best_record = key, r

    if best_record is not None:
        return DescriptionMatch(description=best_record["description"], match_type="silver_fuzzy", matched_silver_slug=best_record["slug"])

    fallback = _source_doc_intro(scheme_id, raw_documents_dir)
    if fallback:
        return DescriptionMatch(description=fallback, match_type="source_doc_fallback")

    return DescriptionMatch(description="", match_type="no_description")


def build_discovery_index(
    gold_dir: Path,
    silver_jsonl_path: Path,
    raw_documents_dir: Path,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> tuple[LocalIndex, dict[str, DescriptionMatch]]:
    """Returns (index, gold_match_report) — the match report is returned separately (not just
    logged) so a caller (report, UI, tests) can surface which gold schemes fell back to which
    match tier, per Part B's explicit "flag any gold scheme with no silver match" instruction."""
    raw_records = [json.loads(line) for line in silver_jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    # Mojibake cleanup (Bug 3 fix) applied here, once, at the same point this module independently
    # re-parses the raw JSONL (shared.py's own get_silver_records() parses it separately for the
    # rest of the app -- two parse points, both need the fix, or shortlist card/search text stays
    # corrupted even after the app-side fix).
    silver_records = [clean_record_text(r) for r in raw_records]

    index = LocalIndex(model_name=model_name)
    chunks: list[DocumentChunk] = []

    gold_match_report: dict[str, DescriptionMatch] = {}
    for scheme_id, name in GOLD_SCHEME_NAMES.items():
        match = resolve_gold_description(scheme_id, silver_records, raw_documents_dir)
        gold_match_report[scheme_id] = match
        text = f"{name}. {match.description}".strip()
        chunks.append(
            DocumentChunk(
                doc_id=scheme_id, scheme_id=scheme_id, effective_date=None,
                citation=f"gold scheme ({match.match_type})", source_path=str(gold_dir / f"{scheme_id}.json"),
                chunk_index=0, text=text, source_type="gold",
            )
        )

    for r in silver_records:
        if not r.get("scheme_name"):
            continue
        text = f"{r['scheme_name']}. {r.get('description') or ''}".strip()
        chunks.append(
            DocumentChunk(
                doc_id=r["slug"], scheme_id=r["slug"], effective_date=None,
                citation=r.get("official_link", ""), source_path="data/silver/schemes.jsonl",
                chunk_index=0, text=text, source_type="silver_unverified",
            )
        )

    index.add_chunks(chunks)
    return index, gold_match_report


def search(index: LocalIndex, query: str, top_k: int = 8, min_gold_slots: int = 2) -> list[tuple[DocumentChunk, float]]:
    """NOT a plain top-k-by-raw-score passthrough — deliberately. Tested against the real 2073
    -record index: for the query "old age pension", IGNOAPS (gold, the single most relevant,
    verified match) ranked 78th by raw cosine score, comfortably outside any reasonable top_k,
    purely because gold's indexed text (scheme name + one fetched description) is statistically
    out-competed by the much larger and often more keyword-dense 2000+-record silver corpus. A
    discovery layer whose whole point is a Verified/Unverified badge is broken if verified results
    are effectively never reachable in the shortlist — so this guarantees up to `min_gold_slots`
    gold results appear (if any score at all within a generously wide net), filling the rest of
    `top_k` with the best-scoring silver results, then re-sorts the merged set by score."""
    wide_net = index.query(query, top_k=max(top_k * 20, 200))
    gold = [r for r in wide_net if r[0].source_type == "gold"][:min_gold_slots]
    silver_slots = max(top_k - len(gold), 0)
    silver = [r for r in wide_net if r[0].source_type != "gold"][:silver_slots]
    merged = gold + silver
    merged.sort(key=lambda r: r[1], reverse=True)
    return merged[:top_k]
