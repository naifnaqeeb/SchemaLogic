"""Run Baseline 2 (direct-LLM eligibility answering, plan Section 7) over the gold profile suites.

LIVE: makes real LLM calls and spends provider quota. Not part of the test suite.

    PYTHONPATH=. python scripts/run_baseline2.py                 # every gold scheme not yet run
    PYTHONPATH=. python scripts/run_baseline2.py PMAY-G AB-PMJAY # explicit order
    B2_TOKEN_BUDGET=80000 PYTHONPATH=. python scripts/run_baseline2.py

The methodology -- prompt, verdict parsing, and the directional classification of disagreements
against the real symbolic evaluator -- lives in schemelogic/evaluation/direct_llm_baseline.py.
This file only orchestrates: picking schemes, pacing, budget stops, recovery, and writing results.

History: the 2026-09-19 run was driven by an uncommitted scratch script that was later lost to a
temp-directory cleanup, leaving its committed results with no way to regenerate them from the
repo. This is that runner rebuilt and committed, behaving the same way, so every
baseline2_direct_llm_*.json in data/extraction_runs/ can be reproduced from source.

Behaviour that matters for interpreting results:
  - Whole schemes only. A scheme is started only if its projected cost fits the remaining budget,
    so a stop never leaves a half-measured scheme that can't be quoted.
  - Two passes, same as 2026-09-19. Pass 1 uses the module's default completion cap. Any profile
    that fails with json_validate_failed -- gpt-oss spending its whole completion budget on
    reasoning tokens, a mechanical failure rather than a judgement -- is retried once with a
    larger cap, same prompt and model, and marked `recovered_with_higher_max_tokens`.
  - Stops cleanly on the token budget or on a per-day (TPD) 429, keeping everything already done.
  - Token figures are ESTIMATES: llm/provider.py's ProviderResult does not surface usage, so cost
    is projected from document size rather than measured (unlike the extraction diagnosis runs).
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from schemelogic.evaluation import direct_llm_baseline as dlb  # noqa: E402
from schemelogic.extraction.extractor import _estimate_tokens  # noqa: E402
from schemelogic.schema.models import Scheme  # noqa: E402

RUNS_DIR = ROOT / "data" / "extraction_runs"
ALL_GOLD = ["PM-KISAN", "IGNOAPS", "MH-LADKI-BAHIN", "PM-UJJWALA-2.0", "PMMVY", "PMAY-G", "AB-PMJAY"]
TOKEN_BUDGET = int(os.environ.get("B2_TOKEN_BUDGET", "60000"))
RECOVERY_MAX_TOKENS = 2000
TPM = 8000
_PER_CALL_OVERHEAD = 900  # system prompt + rendered profile + completion, on top of the document
_RECOVERY_RESERVE = 3500  # held back so a recovery call can't push a scheme over budget

_last = {"at": 0.0, "tokens": 0}


def _pace(next_estimate: int) -> None:
    """Keep a rolling minute under the flat TPM ceiling."""
    refilled = (TPM / 60.0) * (time.time() - _last["at"])
    outstanding = max(0.0, _last["tokens"] - refilled)
    if outstanding + next_estimate > TPM - 300:
        time.sleep((outstanding + next_estimate - (TPM - 300)) / (TPM / 60.0) + 1.0)


def _is_truncation(detail: str) -> bool:
    d = detail.lower()
    return "json_validate_failed" in d or "failed to generate json" in d or "failed to validate json" in d


def _is_daily_cap(detail: str) -> bool:
    d = detail.lower()
    return "per day" in d or "tpd" in d


def _already_completed() -> set[str]:
    done: set[str] = set()
    for path in RUNS_DIR.glob("baseline2_direct_llm_*.json"):
        try:
            done.update(json.loads(path.read_text(encoding="utf-8")).get("schemes_completed", []))
        except (OSError, json.JSONDecodeError):
            continue
    return done


def _load(scheme_id: str):
    doc = (ROOT / "data" / "raw_documents" / f"{scheme_id}.md").read_text(encoding="utf-8")
    scheme = Scheme.model_validate(json.loads((ROOT / "data" / "gold" / f"{scheme_id}.json").read_text(encoding="utf-8")))
    raw = json.loads((ROOT / "data" / "profiles" / f"{scheme_id}.json").read_text(encoding="utf-8"))
    return doc, scheme, {k: v for k, v in raw.items() if not k.startswith("_")}


def main(order: list[str]) -> None:
    out_path = RUNS_DIR / f"baseline2_direct_llm_{date.today().isoformat()}.json"
    spent = 0
    attempted: list[str] = []
    reports: list[dict] = []
    stopped_reason: str | None = None
    partial_scheme: str | None = None  # set only when a stop interrupts a scheme mid-way

    for scheme_id in order:
        doc, scheme, profiles = _load(scheme_id)
        per_call = _estimate_tokens(doc) + _PER_CALL_OVERHEAD
        projected = per_call * len(profiles)
        if spent + projected + _RECOVERY_RESERVE > TOKEN_BUDGET:
            stopped_reason = (f"budget: {scheme_id} needs ~{projected:,} (+{_RECOVERY_RESERVE:,} recovery "
                              f"reserve), only {TOKEN_BUDGET - spent:,} left")
            print(f"[budget] stopping before {scheme_id}: {stopped_reason}", flush=True)
            break

        attempted.append(scheme_id)
        report = dlb.SchemeBaselineReport(scheme_id=scheme_id)
        recovered: set[str] = set()
        print(f"\n=== {scheme_id}: {len(profiles)} profiles (~{projected:,} tok) ===", flush=True)

        for pid, profile in profiles.items():
            answer = None
            for attempt, cap in enumerate((None, RECOVERY_MAX_TOKENS)):
                estimate = per_call if cap is None else per_call + cap
                _pace(estimate)
                kwargs = {} if cap is None else {"max_tokens": cap}
                result = dlb.ask_direct(doc, profile, scheme_name=scheme_id, **kwargs)
                spent += estimate
                report.tokens_used += estimate
                _last.update(at=time.time(), tokens=estimate)

                if isinstance(result, dlb.DirectAnswer):
                    answer = result
                    if attempt == 1:
                        recovered.add(pid)
                    break
                if _is_daily_cap(result.detail):
                    stopped_reason = "daily token cap (TPD) reached"
                    report.failures.append(f"{pid}: {result.detail[:200]}")
                    break
                if attempt == 0 and _is_truncation(result.detail):
                    print(f"  {pid:46} truncated at default cap -> retrying at {RECOVERY_MAX_TOKENS}", flush=True)
                    continue
                report.failures.append(f"{pid}: {result.detail[:200]}")
                break

            if stopped_reason:
                partial_scheme = scheme_id
                print(f"  [ABORT] {stopped_reason}", flush=True)
                break
            if answer is None:
                print(f"  {pid:46} FAILURE {report.failures[-1][:90]}", flush=True)
                continue

            c = dlb.compare_profile(scheme, pid, profile, answer)
            report.comparisons.append(c)
            flag = "" if c.relation == "agree" else f"  <-- {c.relation}"
            rec = " [recovered]" if pid in recovered else ""
            print(f"  {pid:46} llm={c.baseline_verdict:11} eval={c.evaluator_verdict:26}{rec}{flag}", flush=True)

        d = report.to_dict()
        for row in d["comparisons"]:
            if row["profile_id"] in recovered:
                row["recovered_with_higher_max_tokens"] = True
        reports.append(d)
        print(f"  -> agreement {report.agreement_rate:.0%}, harmful-positive {report.harmful_positive_rate:.0%}, "
              f"{report.counts()}", flush=True)
        if stopped_reason:
            break

    payload = {
        "run": "baseline2_direct_llm",
        "date": date.today().isoformat(),
        "methodology_module": "schemelogic/evaluation/direct_llm_baseline.py",
        "model": "provider default (openai/gpt-oss-120b via Groq)",
        "token_budget": TOKEN_BUDGET,
        "tokens_spent_estimated": spent,
        "token_note": "ESTIMATED from document size; ProviderResult does not surface usage.",
        "recovery": f"json_validate_failed profiles retried once at max_tokens={RECOVERY_MAX_TOKENS}, same prompt/model",
        # A budget stop happens BEFORE a scheme starts, so every report written is complete; only a
        # mid-scheme abort (TPD) leaves a partial one, and that one must not be quoted as covered.
        "schemes_completed": [r["scheme_id"] for r in reports if r["scheme_id"] != partial_scheme],
        "schemes_partial": [partial_scheme] if partial_scheme else [],
        "schemes_attempted": attempted,
        "schemes_not_attempted": [s for s in order if s not in attempted],
        "stopped_reason": stopped_reason,
        "reports": reports,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\ntokens spent (estimated): {spent:,} / {TOKEN_BUDGET:,}")
    print(f"completed: {payload['schemes_completed']}")
    print(f"not attempted: {payload['schemes_not_attempted']}")
    print(f"stopped_reason: {stopped_reason}")
    print(f"output: {out_path}")


if __name__ == "__main__":
    explicit = [a for a in sys.argv[1:] if not a.startswith("-")]
    done = _already_completed()
    order = explicit or [s for s in ALL_GOLD if s not in done]
    skipped = [s for s in order if s in done]
    if skipped:
        print(f"[skip] already completed in an earlier run: {skipped}", flush=True)
    main([s for s in order if s not in done])
