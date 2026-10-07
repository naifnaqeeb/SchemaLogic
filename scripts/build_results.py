"""Build RESULTS.md from every report of the final push -- item 12. Offline: no LLM calls.

    PYTHONPATH=. python scripts/build_results.py

Regenerates each offline report from what is on disk (batch report, self-consistency, gate
re-validation, temporal C4, cross-lingual C2 once its Marathi arm exists, RAG summary), then stitches
them into RESULTS.md with a status table on top saying what is complete, partial or still to run.
Re-run after the background runs land; never edit RESULTS.md by hand.
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.conversational import messages  # noqa: E402
from schemelogic.experiments import harness  # noqa: E402

RESULTS_DIR = ROOT / "docs" / "results"
OUT = ROOT / "RESULTS.md"


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def regenerate() -> None:
    with redirect_stdout(io.StringIO()):
        _script("run_batch_report").main()
        _script("analyze_self_consistency").main()
        _script("analyze_gate_revalidation").main()
        temporal = _script("run_temporal_case_study")
        s = temporal.score()
        (harness.EXPERIMENTS_DIR / f"temporal_c4_{s['date']}.json").write_text(
            json.dumps(s, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (RESULTS_DIR / "TEMPORAL_C4.md").write_text(temporal.markdown(s), encoding="utf-8")
        if any((harness.EXPERIMENTS_DIR / "temporal_c4" / "MH-LADKI-BAHIN__marathi_GRs_in_order").glob("sample_*.json")):
            _script("analyze_cross_lingual").main()


def _embed(name: str) -> str:
    """A generated report, its title dropped and every heading moved one level down."""
    path = RESULTS_DIR / name
    if not path.exists():
        return "*Not generated yet.*\n"
    lines = path.read_text(encoding="utf-8").splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    return "\n".join("#" + ln if re.match(r"#{1,5} ", ln) else ln for ln in lines).strip() + "\n"


def _rag() -> str:
    rows = _script("run_rag_comparison").summarize()["rows"]
    if all(r["status"] == "not run" for r in rows):
        return "*Not run yet* (queued after the gate re-validation).\n"
    out = ["| Scheme | Arm | Status | Findings | Temporal findings | Found the gold's supersession | Gate on it |",
           "|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['scheme']} | {r['arm']} | {r['status']} | {r.get('findings', '')} | {r.get('temporal_findings', '')} | "
                   f"{r.get('found_gold_supersession', '')} | {r.get('gate_on_it') or ''} |")
    return "\n".join(out) + "\n\nOne judge call per arm: a single sample, not a rate.\n"


def _translations() -> str:
    out = ["| Language | State | Translated | Reviewed by a person | Catalogue |", "|---|---|---|---|---|"]
    for lang in messages.LANGUAGES:
        s = messages.review_status(lang)
        out.append(f"| {messages_name(lang)} | {s['state']} | {s['translated']} | {s['reviewed']} | {s['total']} |")
    return "\n".join(out) + ("\n\n\"machine\": machine-translated and not yet reviewed; the app says so on every page. "
                             "Review sheets: `docs/i18n/REVIEW_<lang>.csv`.\n")


def messages_name(lang: str) -> str:
    from schemelogic.conversational.language import LANGUAGE_NAMES
    return LANGUAGE_NAMES.get(lang, lang)


def _status() -> str:
    progress = dict(_script("queue_status").progress())
    rows = [("Batch report: pipeline 2026-08, Baseline 3, Baseline 2", "complete", "batch report"),
            ("Full pipeline on Baseline 3's extraction", progress["pipeline on sample 1"], "batch report"),
            ("Retries of failed judge calls (max_tokens=2000, then reasoning_effort=low)", progress["pipeline retry (failed judge calls)"], "batch report"),
            ("Baseline 1 (flat attributes)", progress["baseline 1"], "batch report"),
            ("Self-consistency k=3 (PMMVY samples)", progress["k=3 self-consistency, PMMVY"], "self-consistency"),
            ("pmksypdmc confidence test", progress["k=3 pmksypdmc (silver)"], "self-consistency"),
            ("Gate re-validation, judge runs", progress["gate re-validation"], "gate re-validation"),
            ("Temporal C4 + Marathi arm of C2", progress["temporal C4 + Marathi C2 arm"], "temporal / cross-lingual"),
            ("RAG with/without retrieval", progress["RAG with/without retrieval"], "RAG")]
    out = ["| Experiment | Done | Section |", "|---|---|---|"]
    for name, done, section in rows:
        n, _, total = done.partition("/")
        state = done if done == "complete" else (f"{done} — complete" if n == total else (f"{done} — **partial**" if n != "0" else f"{done} — **not run yet**"))
        out.append(f"| {name} | {state} | {section} |")
    return "\n".join(out) + "\n"


def build() -> str:
    head = harness.result_header("results", "groq", {})
    parts = [
        "# Results — SchemeLogic final push",
        "",
        f"*Built {datetime.now().isoformat(sep=' ', timespec='minutes')} by `scripts/build_results.py` from code "
        f"`{head['code_commit'][:7]}`, against gold frozen at `{harness.GOLD_TAG}` (`{head['gold_commit'][:7]}`). "
        f"Model `{harness.MODEL}` on Groq's free tier. Regenerate; don't edit.*",
        "",
        "**Every sample here is small** (7 gold schemes, 8–14 profiles each, k=3, ~30 injected errors, k=1 per "
        "pre-amendment text). Read directions, not decimals. The caveats and the withdrawn claims are in §1. "
        "The one-page review summary is [docs/results/REVIEW_SUMMARY.md](docs/results/REVIEW_SUMMARY.md).",
        "",
        "## Status",
        "",
        _status(),
        "## 1. Extraction, pipeline and baselines against gold",
        "",
        _embed("BATCH_REPORT.md"),
        "## 2. Self-consistency confidence",
        "",
        _embed("SELF_CONSISTENCY.md"),
        "## 3. Gate re-validation on injected errors",
        "",
        _embed("GATE_REVALIDATION.md"),
        "## 4. Temporal case study (C4)",
        "",
        _embed("TEMPORAL_C4.md"),
        "## 5. Cross-lingual case study (C2)",
        "",
        _embed("CROSS_LINGUAL_C2.md") if (RESULTS_DIR / "CROSS_LINGUAL_C2.md").exists() else "*Not run yet* (the Marathi arm is queued with the temporal case study).\n",
        "## 6. RAG: the judge with and without retrieval",
        "",
        _rag(),
        "## 7. Translations",
        "",
        _translations(),
    ]
    return "\n".join(parts)


if __name__ == "__main__":
    regenerate()
    OUT.write_text(build(), encoding="utf-8")
    print(f"written: {OUT.relative_to(ROOT)}")
