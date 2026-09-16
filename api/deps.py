"""FastAPI-side resource loading. Mirrors schemelogic/conversational/shared.py's wiring exactly,
minus the Streamlit dependency: shared.py's @st.cache_resource/@st.cache_data decorators are tied
to Streamlit's script-rerun model, which doesn't exist in a FastAPI process, so this uses plain
functools.lru_cache instead (built once, at first request, reused for the process lifetime --
same intent as shared.py's caching, different plumbing for a different host).

Every call here goes straight into existing, untouched business-logic modules (discovery/,
ingestion/) -- this file adds no new logic, only a second (Streamlit-free) way to construct the
same ChatDeps shared.py already builds for the Streamlit app.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from schemelogic.conversational.chat_engine import ChatDeps
from schemelogic.discovery.indexer import DescriptionMatch, build_discovery_index
from schemelogic.ingestion.silver_scraper import clean_record_text
from schemelogic.retrieval.indexer import LocalIndex

ROOT = Path(__file__).resolve().parents[1]
GOLD_DIR = ROOT / "data" / "gold"
SILVER_PATH = ROOT / "data" / "silver" / "schemes.jsonl"
RAW_DOCS_DIR = ROOT / "data" / "raw_documents"


@lru_cache(maxsize=1)
def get_discovery_index() -> tuple[LocalIndex, dict[str, DescriptionMatch]]:
    return build_discovery_index(gold_dir=GOLD_DIR, silver_jsonl_path=SILVER_PATH, raw_documents_dir=RAW_DOCS_DIR)


@lru_cache(maxsize=1)
def get_silver_records() -> list[dict]:
    if not SILVER_PATH.exists():
        return []
    records = [json.loads(line) for line in SILVER_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [clean_record_text(r) for r in records]


@lru_cache(maxsize=1)
def get_silver_by_slug() -> dict:
    return {r["slug"]: r for r in get_silver_records()}


def gold_match_report() -> dict[str, DescriptionMatch]:
    _index, match_report = get_discovery_index()
    return match_report


def build_deps(language: str = "en") -> ChatDeps:
    index, match_report = get_discovery_index()
    return ChatDeps(
        discovery_index=index,
        gold_match_report=match_report,
        silver_by_slug=get_silver_by_slug(),
        raw_docs_dir=RAW_DOCS_DIR,
        gold_dir=GOLD_DIR,
        language=language,
    )
