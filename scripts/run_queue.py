"""Run a day's quota-heavy items in order, waiting for Groq's rolling 24h window rather than pushing
through it. LIVE.

    PYTHONPATH=. python scripts/run_queue.py day2 [--budget=175000] [--max-hours=20]

Each item is one of the resumable runners; a runner that stops on the budget is resumed once the
ledger shows enough of the window has freed (harness.seconds_until_headroom). A Groq daily-cap 429 --
Groq's window can include usage from before the ledger existed -- backs off 30 minutes; a per-minute
rate limit backs off 2 minutes. Gives up cleanly after --max-hours. Log lines are timestamped.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.experiments import harness  # noqa: E402


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def queue(name: str, budget: int):
    """(label, estimate of the next call, callable returning a runner stop reason)."""
    gold = harness.gold_scheme_ids()
    sc, p1, b1 = _script("run_self_consistency"), _script("run_pipeline_on_samples"), _script("run_baseline1")
    if name == "day2":
        return [
            ("k=3 self-consistency (finish)", sc.ESTIMATE_PER_SAMPLE, lambda: sc.run(gold, 3, budget)),
            ("k=3 pmksypdmc (silver)", sc.ESTIMATE_PER_SAMPLE, lambda: sc.run(["_silver_pmksypdmc"], 3, budget)),
            ("pipeline on sample 1", p1.ESTIMATE, lambda: p1.run(gold, budget)),
            ("baseline 1", b1.ESTIMATE, lambda: b1.run(gold, budget)),
        ]
    raise SystemExit(f"unknown queue {name!r}")


def main(name: str, budget: int, max_hours: float) -> None:
    deadline = time.time() + max_hours * 3600
    for label, estimate, step in queue(name, budget):
        while True:
            _log(f"{label}: start (rolling 24h {harness.tokens_spent_rolling():,})")
            reason = step()
            _log(f"{label}: {reason}")
            if reason == "done":
                break
            wait = {"budget": max(60.0, harness.seconds_until_headroom(estimate, budget) + 60),
                    "daily_cap": 1800.0, "rate_limited": 120.0}.get(reason, 1800.0)
            if time.time() + wait > deadline:
                _log(f"stopping: next attempt would pass the {max_hours}h limit")
                return
            _log(f"{label}: waiting {wait / 60:.0f} min")
            time.sleep(wait)
    _log("queue done")


if __name__ == "__main__":
    args = sys.argv[1:]
    budget = int(next((a.split("=", 1)[1] for a in args if a.startswith("--budget=")), 175_000))
    hours = float(next((a.split("=", 1)[1] for a in args if a.startswith("--max-hours=")), 20))
    main(next(a for a in args if not a.startswith("-")), budget, hours)
