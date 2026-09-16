"""GET /schemes, GET /schemes/{id} -- thin pass-through wrapping the exact same logic the
Streamlit browse page (schemelogic/conversational/pages/1_Browse_all_schemes.py) uses: gold names
from discovery.indexer.GOLD_SCHEME_NAMES, silver records via api.deps (mojibake-cleaned, same as
shared.py), and the deterministic keyword-category heuristic from discovery/categories.py. No new
categorization/filtering logic -- same function, same behavior, just returned as JSON instead of
rendered as Streamlit cards.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from schemelogic.discovery.categories import CATEGORIES, categories_for
from schemelogic.discovery.indexer import GOLD_SCHEME_NAMES

from . import deps as api_deps

router = APIRouter()


def _all_rows() -> list[dict]:
    gold_rows = [
        {
            "id": scheme_id, "name": name, "source_type": "gold", "description": None,
            "categories": sorted(categories_for(name)),
        }
        for scheme_id, name in sorted(GOLD_SCHEME_NAMES.items(), key=lambda kv: kv[1])
    ]
    silver_rows = [
        {
            "id": r["slug"], "name": r.get("scheme_name") or r["slug"], "source_type": "silver",
            "description": r.get("description"),
            "categories": sorted(categories_for(r.get("scheme_name") or "", r.get("description"))),
        }
        for r in api_deps.get_silver_records()
        if r.get("scheme_name")
    ]
    return gold_rows + silver_rows


@router.get("/schemes")
def list_schemes(query: str = "", category: str = "all", limit: int = 60, offset: int = 0) -> dict:
    rows = _all_rows()
    q = query.strip().lower()
    if q:
        rows = [r for r in rows if q in r["name"].lower()]
    if category != "all":
        rows = [r for r in rows if category in r["categories"]]
    total = len(rows)
    return {
        "total": total,
        "categories": list(CATEGORIES),
        "results": rows[offset : offset + max(limit, 0)],
    }


@router.get("/schemes/{scheme_id}")
def get_scheme(scheme_id: str) -> dict:
    for row in _all_rows():
        if row["id"] == scheme_id:
            return row
    raise HTTPException(status_code=404, detail="scheme not found")
