"""Shared harness for the final-push experiments (docs/PLAN_FINAL_PUSH.md).

- Frozen gold: every experiment reads gold and profiles from the `gold-v2` tag in git, not the working
  tree, so a later gold edit can never leak into a result.
- Result header: every result file records the gold tag, the commit the run came from, provider,
  model, configuration and date.
- Token ledger: every LLM call's MEASURED usage (the response's `usage`, not an estimate) is appended
  to data/experiments/token_ledger.jsonl. A daily budget (default 180k tokens, a margin under Groq's
  ~200k daily cap) is checked before each call, and calls are paced under Groq's 8,000 tokens/minute.
- Stopping: a daily-cap (TPD) rate limit or an exhausted budget stops a run cleanly; a run re-started
  later skips the work it already saved.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from schemelogic.schema.models import Scheme

ROOT = Path(__file__).resolve().parents[2]
GOLD_TAG = "gold-v2"
MODEL = "openai/gpt-oss-120b"
EXPERIMENTS_DIR = ROOT / "data" / "experiments"
LEDGER = EXPERIMENTS_DIR / "token_ledger.jsonl"
DAILY_BUDGET = 180_000
TPM_LIMIT = 8_000
TPM_TARGET = 7_600  # pace below the limit: the estimate before a call is only an estimate


class BudgetExhausted(Exception):
    """The day's token budget would be exceeded, or the provider reported its daily cap."""


# --- frozen gold ---------------------------------------------------------------------------------


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8")


def gold_commit() -> str:
    return _git("rev-list", "-n", "1", GOLD_TAG).strip()


def head_commit() -> str:
    return _git("rev-parse", "--short", "HEAD").strip()


def gold_scheme_ids() -> list[str]:
    names = _git("ls-tree", "--name-only", f"{GOLD_TAG}:data/gold").split()
    return sorted(n[: -len(".json")] for n in names if n.endswith(".json"))


def frozen_gold(scheme_id: str) -> Scheme:
    return Scheme.model_validate_json(_git("show", f"{GOLD_TAG}:data/gold/{scheme_id}.json"))


def frozen_profiles(scheme_id: str) -> dict[str, dict]:
    raw = json.loads(_git("show", f"{GOLD_TAG}:data/profiles/{scheme_id}.json"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def source_document(scheme_id: str) -> tuple[str, str]:
    """(text, sha256) of the scheme's extraction input. The raw documents are gitignored, so the hash
    is what ties a result to the exact text."""
    text = (ROOT / "data" / "raw_documents" / f"{scheme_id}.md").read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def result_header(item: str, provider: str, config: dict[str, Any], model: str = MODEL) -> dict[str, Any]:
    return {
        "item": item, "gold_tag": GOLD_TAG, "gold_commit": gold_commit(), "code_commit": head_commit(),
        "provider": provider, "model": model, "config": config,
        "date": date.today().isoformat(), "created_at": datetime.now().isoformat(timespec="seconds"),
    }


# --- token ledger, budget and pacing -------------------------------------------------------------


def _ledger_rows() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()]


def tokens_spent(day: str | None = None) -> int:
    """Tokens recorded on one calendar day (for reports)."""
    day = day or date.today().isoformat()
    return sum(r.get("total_tokens") or 0 for r in _ledger_rows() if r.get("date") == day)


def tokens_spent_rolling(hours: float = 24, now: datetime | None = None) -> int:
    """Tokens recorded in the last `hours` -- what the budget is checked against, because Groq's
    daily cap is a rolling window, not a calendar day (found 2026-10-05: a run stopped on Groq's daily
    cap after 97.6k tokens of that calendar day, with the previous evening's runs still in the window)."""
    now = now or datetime.now()
    total = 0
    for r in _ledger_rows():
        try:
            age = (now - datetime.fromisoformat(r["ts"])).total_seconds()
        except (KeyError, ValueError):
            continue
        if 0 <= age < hours * 3600:
            total += r.get("total_tokens") or 0
    return total


def seconds_until_headroom(needed: int, budget: int = DAILY_BUDGET, now: datetime | None = None) -> float:
    """How long until the rolling-24h total leaves room for `needed` more tokens under `budget`: the
    window frees each row 24h after it was recorded."""
    now = now or datetime.now()
    rows = []
    for r in _ledger_rows():
        try:
            ts = datetime.fromisoformat(r["ts"])
        except (KeyError, ValueError):
            continue
        if 0 <= (now - ts).total_seconds() < 86400:
            rows.append((ts, r.get("total_tokens") or 0))
    total = sum(n for _, n in rows)
    for ts, n in sorted(rows):
        if total + needed <= budget:
            break
        total -= n
        wait = (ts - now).total_seconds() + 86400
        if total + needed <= budget:
            return max(0.0, wait)
    return 0.0 if total + needed <= budget else 86400.0


class Ledger:
    """Records measured usage for one experiment item, enforces the daily budget, paces per minute."""

    def __init__(self, item: str, provider: str, daily_budget: int = DAILY_BUDGET, model: str = MODEL,
                 sleep=time.sleep, clock=time.time):
        self.item, self.provider, self.model = item, provider, model
        self.daily_budget, self._sleep, self._clock = daily_budget, sleep, clock
        self._recent: list[tuple[float, int]] = []  # (timestamp, tokens) within the last minute
        self.spent_this_run = 0

    def before_call(self, estimate: int) -> None:
        """Raise BudgetExhausted if `estimate` more tokens would cross today's budget; otherwise wait
        until the last minute's usage leaves room for it under Groq's per-minute limit."""
        spent = tokens_spent_rolling()
        if spent + estimate > self.daily_budget:
            raise BudgetExhausted(f"24h budget {self.daily_budget:,}: {spent:,} spent in the last 24h, next call ~{estimate:,}")
        while True:
            now = self._clock()
            self._recent = [(t, n) for t, n in self._recent if now - t < 60]
            used = sum(n for _, n in self._recent)
            if used + estimate <= TPM_TARGET or not self._recent:
                return
            self._sleep(max(1.0, 60 - (now - self._recent[0][0])))

    def record(self, usage: dict, scheme_id: str | None = None, **extra: Any) -> None:
        total = usage.get("total_tokens") or (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)
        self._recent.append((self._clock(), total))
        self.spent_this_run += total
        EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
        row = {"date": date.today().isoformat(), "ts": datetime.now().isoformat(timespec="seconds"),
               "item": self.item, "scheme_id": scheme_id, "provider": self.provider, "model": self.model,
               **usage, "total_tokens": total, **extra}
        with LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")


def is_daily_cap(detail: str) -> bool:
    """Groq's daily (TPD/RPD) limit -- unlike the per-minute one, it can't be waited out."""
    d = detail.lower()
    return "tokens per day" in d or "tpd" in d or "requests per day" in d or "rpd" in d
