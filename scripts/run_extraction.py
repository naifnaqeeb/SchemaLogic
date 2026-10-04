"""One ontology-constrained extraction of a scheme's source document -- the Phase 3 "draft" step.

LIVE: one extraction (two LLM calls, ~7-9k tokens). Not part of the test suite.

    PYTHONPATH=. python scripts/run_extraction.py PMAY-G --label=updated-doc

Reads data/raw_documents/<scheme>.md, writes data/extraction_runs/<scheme>_gpt-oss-120b_ontology_<label>_<ts>.json
in the shape of the 2026-08 ontology runs (`draft_extraction`), plus the document's SHA-256: the raw
documents are gitignored, so the hash is what ties a draft to the exact text it was extracted from.
Same default extractor configuration as those runs (no reasoning_effort, full ontology).
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.extraction.extractor import ExtractionFailure, extract_scheme  # noqa: E402


def main(scheme_id: str, label: str) -> None:
    doc_path = ROOT / "data" / "raw_documents" / f"{scheme_id}.md"
    text = doc_path.read_text(encoding="utf-8")
    result = extract_scheme(text)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    out = ROOT / "data" / "extraction_runs" / f"{scheme_id}_gpt-oss-120b_ontology_{label}_{stamp}.json"
    payload = {
        "scheme_id": scheme_id, "model": "openai/gpt-oss-120b", "run_timestamp": datetime.now().isoformat(),
        "note": f"Ontology-constrained extraction run ({label}).",
        "source_document": f"data/raw_documents/{scheme_id}.md",
        "source_document_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "gold_reference": f"data/gold/{scheme_id}.json",
    }
    if isinstance(result, ExtractionFailure):
        payload["failure"] = {"reason": result.reason, "detail": result.detail}
    else:
        payload["draft_extraction"] = result.model_dump(mode="json", by_alias=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{'FAILED: ' + result.reason if isinstance(result, ExtractionFailure) else 'ok'} -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    labels = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--label=")]
    main(next(a for a in sys.argv[1:] if not a.startswith("-")), labels[0] if labels else "rerun")
