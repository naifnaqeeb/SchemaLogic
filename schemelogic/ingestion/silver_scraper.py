"""Silver-set ingestion (Phase 3 checkpoint pivot): scraped, unverified breadth, not gold.

Deliberately low/no-LLM-cost. Every record here is myScheme.gov.in's OWN encoding of a scheme's
eligibility text — parsed with plain regex/string heuristics, never passed through the
extraction/judge/gate pipeline. There is no "draft vs gold" comparison for silver records: they
ARE the source, not an LLM's reading of the source. `source_tag()` on every record is
"myscheme_unverified" so a silver record can never be mistaken for a gold one anywhere in the
codebase.

Reuses an existing scraped corpus (shrijayan/gov_myscheme on Hugging Face, Apache-2.0 licensed,
attribution: "Data derived from the Indian Government's myScheme portal (myscheme.gov.in) via the
shrijayan/gov_myscheme Hugging Face dataset") rather than re-scraping myscheme.gov.in from
scratch — that dataset's own README advertises ready CSV/JSON/Parquet exports, but the actual
repository (verified via the HF tree API, 2026-08) contains only a `text_data/` folder of 723
per-scheme PDF "print captures" of the site — no structured export is actually present despite
the README's claim. Filenames are duplicated under multiple naming variants (` copy.pdf`,
`(1).pdf`, `(1) copy.pdf`, ...) all sharing an identical content hash; deduping by content hash
(not filename pattern) found 2067 unique schemes, not the 723 the README states.

Each PDF is myscheme.gov.in's scheme-detail page as rendered (all UI chrome included: nav labels,
modal-dialog text, duplicated content blocks from what looks like two renders of the same
component). The page template is consistent across schemes: scheme name, then a nav tab list
(Details/Benefits/Eligibility/[Exclusions]/Application Process/Documents Required/Frequently
Asked Questions/Sources And References — Exclusions is present only for some schemes), then the
real content in that same section order. Parsing anchors on the SECOND occurrence of "Details" in
the text (the first is the nav tab list itself) and slices sequentially forward from there, so
each section label is only ever matched in its real content position, not the nav preamble.
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pypdf import PdfReader

HF_DATASET = "shrijayan/gov_myscheme"
HF_TREE_API = f"https://huggingface.co/api/datasets/{HF_DATASET}/tree/main/text_data?limit=1000"
HF_RESOLVE_BASE = f"https://huggingface.co/datasets/{HF_DATASET}/resolve/main"
MYSCHEME_BASE_URL = "https://www.myscheme.gov.in/schemes"

SOURCE_TAG = "myscheme_unverified"
"""Set on every SilverRecord. Never used for gold. Check this tag, not the record's shape, when
deciding whether data can be trusted as verified — silver records are never routed through
extraction/judge/gate and carry no confidence score, no source_clause, no human review."""

_SIGN_OUT_MARKER = "Are you sure you want to sign out?"
_ELIGIBILITY_CTA_MARKER = "Check Eligibility"  # distinctive button label, immediately precedes
# ministry/state + repeated scheme name + tags + the real "Details" content marker.
_CONTENT_START_MARKER = "Details"

# India's 28 states + 8 UTs, for classifying a scraped "ministry_or_state" label as a state/UT
# scheme vs. central (a central scheme's label is a Ministry/Department name, which won't exact
# -match any of these). Deliberately a plain exact-match list, not fuzzy matching -- good enough
# for a rough coverage breakdown, not a claim of authoritative classification.
INDIAN_STATES_AND_UTS = {
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat",
    "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh",
    "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal", "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir", "Ladakh",
    "Lakshadweep", "Puducherry",
}

# Source PDFs mis-render curly quotes/apostrophes/Rupee-sign glyphs as a 2-3 codepoint
# mojibake sequence (verified empirically, e.g. what should be one apostrophe glyph decodes
# as the 3 codepoints U+00E2, U+20AC, U+200B) -- a font-CMap bug in the original myScheme
# page captures, not something fixable by choosing a different PDF library. Every such
# sequence starts with U+00E2, and that codepoint practically never occurs in legitimate
# scheme-description English/Hindi prose otherwise, so its bare presence is a reliable proxy
# for "this text has at least one corrupted symbol" without enumerating every 2nd/3rd
# codepoint variant.
_MOJIBAKE_MARKER = "\u00e2"


def has_mojibake(text: str | None) -> bool:
    if not text:
        return False
    return _MOJIBAKE_MARKER in text


def fix_mojibake(text: str | None) -> str | None:
    """Reverses the UTF-8-decoded-as-Windows-1252 corruption described above: re-encoding the
    (already-corrupted) string as cp1252 recovers the original UTF-8 byte sequence, which then
    decodes cleanly -- this is the standard, general fix for this entire mojibake class (curly
    quotes, em/en dashes, the rupee sign, ellipsis, ...), not a table of specific substitutions,
    so it doesn't need updating every time a new corrupted symbol turns up.

    Only touches text that actually contains the marker -- re-encoding already-clean UTF-8 as
    cp1252 can itself corrupt genuine non-ASCII characters (Hindi text, real accented names) that
    were never mojibake in the first place, so this must stay a no-op on clean input.

    `errors="ignore"` on both the re-encode and re-decode: empirically, some records have a SECOND
    kind of corrupted fragment mixed in with the ordinary reversible one -- a stray codepoint (e.g.
    a genuine U+200B zero-width space landing directly in the string, not the U+2039 you'd expect
    from a clean cp1252 decode of that byte) that cp1252 simply cannot encode. Under strict mode
    that one bad codepoint fails the encode() call for the ENTIRE string, so a single unrelated
    stray character was silently blocking every other, perfectly-reversible corruption in the same
    field from ever getting fixed. Dropping just the unencodable fragment (verified empirically to
    be exactly this kind of invisible filler, never visible content) and still fixing everything
    else around it is a strictly better outcome than bailing out on the whole string.

    A leftover BOM (U+FEFF) is stripped unconditionally afterward, whether or not mojibake was
    detected -- some records have one sitting mid-string with no accompanying corruption, and it's
    never a legitimate visible character either way."""
    if not text:
        return text
    if has_mojibake(text):
        try:
            text = text.encode("cp1252", errors="ignore").decode("utf-8", errors="ignore")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass  # belt-and-suspenders -- errors="ignore" above shouldn't raise, but never guess further if it somehow does
    return text.replace("﻿", "")


_TEXT_FIELDS_TO_CLEAN = ("scheme_name", "description", "eligibility_text", "benefits_text", "application_process_text")


def clean_record_text(record: dict) -> dict:
    """Applies fix_mojibake() to every free-text field of a silver record dict. Takes/returns a
    plain dict (not SilverRecord) so it works equally on a freshly-scraped SilverRecord.to_dict()
    and on a record re-loaded from schemes.jsonl by a consumer far downstream (shared.py,
    discovery/indexer.py) that never sees a SilverRecord instance at all."""
    cleaned = dict(record)
    for field_name in _TEXT_FIELDS_TO_CLEAN:
        if field_name in cleaned:
            cleaned[field_name] = fix_mojibake(cleaned[field_name])
    return cleaned


def classify_region(ministry_or_state: str | None) -> str:
    if ministry_or_state and ministry_or_state.strip() in INDIAN_STATES_AND_UTS:
        return "state_or_ut"
    if ministry_or_state:
        return "central_or_other"
    return "unknown"

# UI tab labels in this PDF dump are concatenated with NO separating whitespace between adjacent
# single-word tabs ("BackDetailsBenefitsEligibilityExclusionsApplication Process...") -- there is
# no `\b` word boundary around most of them, so these are plain literal substrings, not `\b`
# -anchored regex. Searched IN ORDER, each starting from the end of the previous match, so a
# label's real section header is never confused with its appearance in the nav-tab preamble
# (the search cursor starts past the preamble entirely, from content_start) or in unrelated prose
# ("Bank Details" inside a Documents-Required list, etc. -- all such collisions live AFTER the
# section they'd be searched from, given document order, so sequential-cursor search skips them).
_SECTION_ANCHORS: list[tuple[str, str]] = [
    ("benefits", "Benefits"),
    ("eligibility", "Eligibility"),
    ("exclusions", "Exclusions"),
    ("application_process", "Application Process"),
    ("documents_required", "Documents Required"),
    ("faq", "Frequently Asked Questions"),
    ("sources", "Sources And References"),
]


@dataclass
class SilverRecord:
    slug: str
    scheme_name: str | None
    description: str | None
    eligibility_text: str | None
    benefits_text: str | None
    application_process_text: str | None
    official_link: str
    ministry_or_state: str | None = None
    source: str = SOURCE_TAG
    sections_found: list[str] = field(default_factory=list)
    parse_warning: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def fetch_file_list() -> list[dict]:
    """Paginate the HF tree API, dedupe by content hash (oid) -- see module docstring for why
    filename-pattern dedup doesn't work on this particular repo."""
    entries: list[dict] = []
    url: str | None = HF_TREE_API
    while url:
        req = urllib.request.Request(url, headers={"User-Agent": "schemelogic-silver-scraper/0.1"})
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            link_header = resp.headers.get("Link")
        entries.extend(json.loads(body))
        m = re.search(r'<([^>]+)>;\s*rel="next"', link_header or "")
        url = m.group(1) if m else None

    by_oid: dict[str, dict] = {}
    for e in entries:
        if e["type"] != "file":
            continue
        existing = by_oid.get(e["oid"])
        if existing is None or len(e["path"]) < len(existing["path"]):
            by_oid[e["oid"]] = e
    return sorted(by_oid.values(), key=lambda e: e["path"])


def download_pdf(entry: dict, dest_dir: Path) -> Path:
    """Downloads (or reuses an already-cached copy of) one PDF. Resumable: reruns skip files
    already on disk, so a partial/interrupted batch run can just be re-invoked."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = Path(entry["path"]).name
    dest = dest_dir / name
    if dest.exists() and dest.stat().st_size == entry["size"]:
        return dest
    url = f"{HF_RESOLVE_BASE}/{entry['path']}"
    req = urllib.request.Request(url, headers={"User-Agent": "schemelogic-silver-scraper/0.1"})
    with urllib.request.urlopen(req) as resp, open(dest, "wb") as out:
        out.write(resp.read())
    return dest


def extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    return "".join(page.extract_text() or "" for page in reader.pages)


def parse_myscheme_pdf_text(raw_text: str, slug: str) -> SilverRecord:
    """Regex/string-heuristic section splitter -- no LLM involved. Missing sections are recorded
    as None (and omitted from sections_found), never guessed."""
    text = _normalize_ws(raw_text)
    official_link = f"{MYSCHEME_BASE_URL}/{slug}"

    sign_out_idx = text.find(_SIGN_OUT_MARKER)
    scheme_name = text[:sign_out_idx].strip() if sign_out_idx != -1 else None
    if not scheme_name:
        return SilverRecord(
            slug=slug, scheme_name=None, description=None, eligibility_text=None,
            benefits_text=None, application_process_text=None, official_link=official_link,
            sections_found=[], parse_warning="scheme_name marker not found — page shape unrecognized",
        )

    cta_idx = text.find(_ELIGIBILITY_CTA_MARKER)
    if cta_idx == -1:
        return SilverRecord(
            slug=slug, scheme_name=scheme_name, description=None, eligibility_text=None,
            benefits_text=None, application_process_text=None, official_link=official_link,
            sections_found=[], parse_warning="'Check Eligibility' CTA marker not found",
        )
    details_idx = text.find(_CONTENT_START_MARKER, cta_idx + len(_ELIGIBILITY_CTA_MARKER))
    if details_idx == -1:
        return SilverRecord(
            slug=slug, scheme_name=scheme_name, description=None, eligibility_text=None,
            benefits_text=None, application_process_text=None, official_link=official_link,
            sections_found=[], parse_warning="'Details' content-start marker not found after CTA",
        )
    content_start = details_idx + len(_CONTENT_START_MARKER)

    # Ministry/state label sits between the CTA and the repeated scheme name that immediately
    # precedes the "Details" content marker, e.g. "...Check EligibilityMinistry Of Agriculture and
    # Farmers WelfarePradhan Mantri Kisan Samman NidhiAgricultural Inputs...Details..." or
    # "...Check EligibilityJammu and KashmirLadies Vocational CentresLadies...Details...".
    cta_end = cta_idx + len(_ELIGIBILITY_CTA_MARKER)
    name_repeat_idx = text.find(scheme_name, cta_end, details_idx)
    ministry_or_state = text[cta_end:name_repeat_idx].strip() or None if name_repeat_idx != -1 else None

    # Sequential anchor slicing: each section's text is [end of this anchor, start of next found
    # anchor). Anchors not found in the document are simply absent from `bounds`.
    bounds: list[tuple[str, int, int]] = []
    cursor = content_start
    for name, label in _SECTION_ANCHORS:
        idx = text.find(label, cursor)
        if idx == -1:
            continue
        bounds.append((name, idx, idx + len(label)))
        cursor = idx + len(label)

    # bounds entries are (name, match_start, match_end). Each section's body is [this match's
    # end, next match's start). description is everything from content_start up to the first
    # matched section header's own start (covers both the "Objective:" sub-label, if present, and
    # any unlabeled intro paragraph before it -- both shapes were observed across sample pages).
    sections: dict[str, str] = {}
    for i, (name, _start, end) in enumerate(bounds):
        section_end = bounds[i + 1][1] if i + 1 < len(bounds) else len(text)
        sections[name] = text[end:section_end].strip()

    description_end = bounds[0][1] if bounds else len(text)
    description = text[content_start:description_end].strip()
    description = re.sub(r"^Objective:?\s*", "", description).strip() or None

    return SilverRecord(
        slug=slug,
        scheme_name=scheme_name,
        description=description,
        eligibility_text=sections.get("eligibility"),
        benefits_text=sections.get("benefits"),
        application_process_text=sections.get("application_process"),
        official_link=official_link,
        ministry_or_state=ministry_or_state,
        sections_found=[n for n, _, _ in bounds],
        parse_warning=None,
    )


def build_silver_dataset(
    raw_pdf_dir: Path,
    out_path: Path,
    limit: int | None = None,
) -> dict:
    """Orchestrates the full batch: list -> download (resumable) -> extract -> parse -> write.
    Never calls an LLM. Returns a coverage/quality summary dict (also written alongside out_path).
    A per-file failure (bad PDF, unrecognized page shape) is recorded as a SilverRecord with
    parse_warning set, not a fatal error for the whole batch."""
    entries = fetch_file_list()
    if limit is not None:
        entries = entries[:limit]

    records: list[SilverRecord] = []
    download_failures: list[dict] = []

    for i, entry in enumerate(entries):
        slug = Path(entry["path"]).stem
        try:
            pdf_path = download_pdf(entry, raw_pdf_dir)
            text = extract_pdf_text(pdf_path)
        except Exception as exc:  # noqa: BLE001 -- batch-scrape: one bad file shouldn't kill the run
            download_failures.append({"path": entry["path"], "error": str(exc)})
            continue
        records.append(parse_myscheme_pdf_text(text, slug))
        if (i + 1) % 100 == 0:
            print(f"processed {i + 1}/{len(entries)}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")

    def _pct(pred) -> float:
        return round(100 * sum(1 for r in records if pred(r)) / len(records), 1) if records else 0.0

    summary = {
        "source": SOURCE_TAG,
        "attribution": (
            "Derived from the Indian Government's myScheme portal (myscheme.gov.in) via the "
            "shrijayan/gov_myscheme Hugging Face dataset (Apache-2.0)."
        ),
        "n_files_listed": len(entries),
        "n_parsed": len(records),
        "n_download_or_extract_failures": len(download_failures),
        "download_failures": download_failures,
        "field_coverage_pct": {
            "scheme_name": _pct(lambda r: bool(r.scheme_name)),
            "description": _pct(lambda r: bool(r.description)),
            "eligibility_text": _pct(lambda r: bool(r.eligibility_text)),
            "benefits_text": _pct(lambda r: bool(r.benefits_text)),
            "application_process_text": _pct(lambda r: bool(r.application_process_text)),
        },
        "n_full_page_shape_unrecognized": sum(1 for r in records if r.parse_warning is not None),
        "n_records_with_exclusions_section": sum(1 for r in records if "exclusions" in r.sections_found),
        "region_breakdown": {
            "state_or_ut": sum(1 for r in records if classify_region(r.ministry_or_state) == "state_or_ut"),
            "central_or_other": sum(1 for r in records if classify_region(r.ministry_or_state) == "central_or_other"),
            "unknown": sum(1 for r in records if classify_region(r.ministry_or_state) == "unknown"),
        },
        "n_records_with_mojibake": sum(
            1 for r in records
            if any(has_mojibake(v) for v in (r.description, r.eligibility_text, r.benefits_text, r.application_process_text))
        ),
    }
    summary_path = out_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary
