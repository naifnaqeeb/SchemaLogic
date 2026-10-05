"""Run control for the background experiment queue (2026-10-05): the live demo shares the Groq quota,
so no experiment call may start after the stop time or on a stop request. No network, no real waiting."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from schemelogic.experiments import harness

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "EXPERIMENTS_DIR", tmp_path)
    monkeypatch.setattr(harness, "LEDGER", tmp_path / "ledger.jsonl")
    (tmp_path / "logs").mkdir()


def _script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _set_stop(when: datetime):
    (harness.control_dir() / "stop_at.txt").write_text(when.isoformat(timespec="minutes"), encoding="utf-8")


def test_no_call_starts_after_the_stop_time_or_on_a_stop_request():
    ledger = harness.Ledger("x", "groq", daily_budget=10**9, sleep=lambda s: None)
    assert harness.stop_reason() is None
    ledger.before_call(1000)  # no stop time: allowed (tests and one-off runs)
    _set_stop(datetime.now() + timedelta(hours=1))
    ledger.before_call(1000)
    _set_stop(datetime.now() - timedelta(minutes=1))
    with pytest.raises(harness.RunStopped):
        ledger.before_call(1000)
    _set_stop(datetime.now() + timedelta(hours=1))
    (harness.control_dir() / "STOP").write_text("x")
    with pytest.raises(harness.BudgetExhausted):  # RunStopped is a BudgetExhausted: every runner stops on it
        ledger.before_call(1000)


def test_queue_refuses_to_start_without_a_future_stop_time():
    q = _script("run_queue")
    assert q.main(["review"], 1, steps=[]) == "no_stop_time"
    _set_stop(datetime.now() - timedelta(minutes=1))
    assert q.main(["review"], 1, steps=[]) == "stopped"


def test_queue_stops_while_waiting_once_the_stop_time_passes():
    q = _script("run_queue")
    _set_stop(datetime.now() + timedelta(hours=1))
    now = [0.0]
    sleeps = []

    def sleep(s):
        sleeps.append(s)
        now[0] += s
        if len(sleeps) == 3:
            (harness.control_dir() / "STOP").write_text("x")

    calls = []
    steps = [("item", 1000, lambda: calls.append(1) or "daily_cap")]
    assert q.main(["review"], 10**9, steps=steps, sleep=sleep, clock=lambda: now[0]) == "stopped"
    assert calls == [1] and max(sleeps) <= q.WAIT_CHUNK  # woke up to check, never slept the whole 30 min
    assert "STOP" in (harness.control_dir() / "queue_state.json").read_text(encoding="utf-8")


def test_review_order_hindi_then_presentable_results_then_other_languages():
    """Order revised 2026-10-05: the demo uses English and Hindi only."""
    labels = [label for label, _, _ in _script("run_queue").queue("review", 1)]
    assert labels[:7] == ["translations hi", "pipeline on sample 1", "temporal C4 (+ Marathi arm of C2)",
                          "pipeline retry: failed judge calls at max_tokens=2000",  # added 2026-10-06
                          "translations ur", "translations mr", "translations ta"]
    assert len(labels) == 12


def test_the_running_order_is_recorded_and_shown_by_queue_status(capsys):
    q = _script("run_queue")
    _set_stop(datetime.now() + timedelta(hours=1))
    steps = [("translations hi", 1, lambda: "done"), ("pipeline on sample 1", 1, lambda: "done")]
    assert q.main(["review"], 10**9, steps=steps) == "done"
    _script("queue_status").status()
    out = capsys.readouterr().out
    assert out.index("1. translations hi") < out.index("2. pipeline on sample 1")


def test_status_reports_progress_without_a_running_queue(capsys):
    status = _script("queue_status")
    status.status()
    out = capsys.readouterr().out
    assert "not running" in out and "NOT SET" in out and "translations hi" in out
