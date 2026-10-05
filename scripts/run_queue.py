"""Run the quota-heavy items in order, waiting for Groq's rolling 24h window rather than pushing
through it. LIVE.

    PYTHONPATH=. python scripts/run_queue.py review [--budget=175000]
    python scripts/queue_status.py --start      # the same, detached so it survives closing VS Code

Each item is one of the resumable runners; a runner that stops on the budget is resumed once the
ledger shows enough of the window has freed (harness.seconds_until_headroom). A Groq daily-cap 429 --
Groq's window can include usage from before the ledger existed -- backs off 30 minutes; a per-minute
rate limit backs off 2 minutes. Log lines are timestamped.

The live demo shares the Groq quota (2026-10-05). The queue therefore refuses to start without a stop
time in the future (data/experiments/logs/stop_at.txt, set by `queue_status.py --set-review`), never
starts a call past it or while a STOP file exists (harness.Ledger.before_call), and waits in chunks of
at most 5 minutes so it exits promptly when either happens. Its state (pid, item, phase) is written to
data/experiments/logs/queue_state.json for `queue_status.py`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.experiments import harness  # noqa: E402

WAIT_CHUNK = 300.0


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def queue(name: str, budget: int):
    """(label, estimate of the next call, callable returning a runner stop reason)."""
    if name != "review":
        raise SystemExit(f"unknown queue {name!r} (day2/day3/day4 were merged into 'review' on 2026-10-05)")
    gold = harness.gold_scheme_ids()
    sc, p1, b1 = _script("run_self_consistency"), _script("run_pipeline_on_samples"), _script("run_baseline1")
    gate, rag = _script("run_gate_revalidation"), _script("run_rag_comparison")
    temporal, tc, export = _script("run_temporal_case_study"), _script("translate_catalogue"), _script("export_ui_strings")

    def translate_and_publish(lang: str) -> str:
        """Translate; once a language is done, regenerate its review sheets and the frontend's UI strings
        and review states (offline), so they are current without anyone being notified."""
        result = tc.translate(lang, budget)
        if result == "done":
            tc.write_sheet(lang)
            export.main()
        return result

    # Order set 2026-10-05 for the review: Hindi first, then the other languages, the full pipeline on
    # sample 1, the temporal case study (with the Marathi arm of C2), then everything else.
    return [
        (f"translations {lang}", tc.ESTIMATE, lambda lang=lang: translate_and_publish(lang)) for lang in ("hi", "ur", "mr", "ta")
    ] + [
        ("pipeline on sample 1", p1.ESTIMATE, lambda: p1.run(gold, budget)),
        ("temporal C4 (+ Marathi arm of C2)", temporal.ESTIMATE_PER_SAMPLE, lambda: temporal.run(budget)),
        ("k=3 self-consistency (finish)", sc.ESTIMATE_PER_SAMPLE, lambda: sc.run(gold, 3, budget)),
        ("k=3 pmksypdmc (silver)", sc.ESTIMATE_PER_SAMPLE, lambda: sc.run(["_silver_pmksypdmc"], 3, budget)),
        ("baseline 1", b1.ESTIMATE, lambda: b1.run(gold, budget)),
        ("gate re-validation (judge on 21 candidates)", gate.ESTIMATE, lambda: gate.run(budget)),
        ("RAG with/without retrieval", rag.ESTIMATE, lambda: rag.run(budget)),
    ]


def _state(**fields) -> None:
    path = harness.control_dir() / "queue_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": os.getpid(), "updated": datetime.now().isoformat(timespec="seconds"), **fields},
                               indent=2), encoding="utf-8")


def _wait(seconds: float, sleep=time.sleep, clock=time.time) -> str | None:
    """Sleep up to `seconds` in chunks; returns a stop reason as soon as one appears."""
    end = clock() + seconds
    while True:
        reason = harness.stop_reason()
        if reason or clock() >= end:
            return reason
        sleep(min(WAIT_CHUNK, max(1.0, end - clock())))


def main(names: list[str], budget: int, steps=None, sleep=time.sleep, clock=time.time) -> str:
    if harness.stop_at() is None:
        _log("refusing to start: no stop time set (python scripts/queue_status.py --set-review ...)")
        return "no_stop_time"
    reason = harness.stop_reason()
    if reason:
        _log(f"refusing to start: {reason}")
        _state(phase="stopped", reason=reason)
        return "stopped"
    _log(f"queue {names}; no call starts after {harness.stop_at().isoformat(timespec='minutes')}")
    for label, estimate, step in steps if steps is not None else [s for name in names for s in queue(name, budget)]:
        while True:
            _state(phase="running", item=label)
            _log(f"{label}: start (rolling 24h {harness.tokens_spent_rolling():,})")
            result = step()
            _log(f"{label}: {result}")
            reason = harness.stop_reason()
            if reason:
                _log(f"stopping: {reason}")
                _state(phase="stopped", item=label, reason=reason)
                return "stopped"
            if result == "done":
                break
            wait = {"budget": max(60.0, harness.seconds_until_headroom(estimate, budget) + 60),
                    "daily_cap": 1800.0, "rate_limited": 120.0}.get(result, 1800.0)
            _log(f"{label}: waiting {wait / 60:.0f} min")
            _state(phase="waiting", item=label, until=datetime.fromtimestamp(clock() + wait).isoformat(timespec="minutes"))
            reason = _wait(wait, sleep, clock)
            if reason:
                _log(f"stopping: {reason}")
                _state(phase="stopped", item=label, reason=reason)
                return "stopped"
    _log("queue done")
    _state(phase="done")
    return "done"


if __name__ == "__main__":
    args = sys.argv[1:]
    budget = int(next((a.split("=", 1)[1] for a in args if a.startswith("--budget=")), 175_000))
    main([a for a in args if not a.startswith("-")] or ["review"], budget)
