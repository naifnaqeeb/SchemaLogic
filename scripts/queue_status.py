"""Check, start and stop the background experiment queue -- one command for each. Offline (no LLM calls).

    python scripts/queue_status.py                                  # alive? where is it? how far has it got?
    python scripts/queue_status.py --set-review "2026-10-08 10:00" --hours-before=24
    python scripts/queue_status.py --start                          # detached: survives closing VS Code
    python scripts/queue_status.py --stop                           # stop now; nothing restarts it
    python scripts/queue_status.py --allow-restart                  # clear a stop (only when told to)

Why (2026-10-05): the live demo shares the Groq quota, and nobody is notified when a background
process finishes, so the stop is enforced three independent ways:
1. the queue itself never starts an LLM call after the stop time or while a STOP file exists
   (harness.Ledger.before_call), and checks again at least every 5 minutes while it waits;
2. a Windows scheduled task ("SchemeLogicQueueStop", created by --set-review) runs `--stop` at the stop
   time -- it writes the STOP file and kills the queue process even if it is stuck -- and is set to run
   as soon as the machine wakes if it was asleep at that time;
3. the queue refuses to start once the stop time has passed or while the STOP file exists, so nothing
   restarts it until `--allow-restart` and a new `--set-review`.
--start launches through WMI (Win32_Process.Create), so the process is not a child of VS Code or of any
terminal and survives closing them. It cannot survive the machine sleeping or shutting down: it pauses
while asleep and stops on shutdown (re-run --start; the runners resume where they stopped).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schemelogic.experiments import harness  # noqa: E402

TASK = "SchemeLogicQueueStop"
LOG = "queue_review.log"


def _alive(pid: int) -> bool:
    if os.name == "nt":  # os.kill(pid, 0) would TERMINATE the process on Windows
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _queue_state() -> dict:
    path = harness.control_dir() / "queue_state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _files(rel: str, pattern: str = "*.json", exclude: tuple[str, ...] = ()) -> int:
    return sum(1 for p in (harness.EXPERIMENTS_DIR / rel).glob(pattern) if p.name not in exclude)


def _retries() -> str:
    """Pipeline runs whose judge call failed with json_validate_failed: retried with reasoning_effort=low
    yet, and how many are still failed (the max_tokens=2000 retry already failed for both)."""
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in (harness.EXPERIMENTS_DIR / "pipeline_on_sample1").glob("*.json")]
    due = [r for r in runs if "json_validate_failed" in (r.get("judge_failure") or {}).get("detail", "")
           or r.get("retried_with_max_tokens") or r.get("retry_settings")]
    done = [r for r in due if "reasoning_low" in r.get("retry_settings", [])]
    still = sum(1 for r in due if r.get("judge_failure"))
    return f"{len(done)}/{len(due)} retried with reasoning_effort=low" + (f"; {still} still failed" if still else "")


def progress() -> list[tuple[str, str]]:
    from schemelogic.conversational import messages

    total = len(messages.catalogue())
    rows = []
    for lang in ("hi", "ur", "mr", "ta"):
        path = messages.I18N_DIR / f"{lang}.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        done = sum(1 for v in data.values() if v.get("text"))
        failed = sum(1 for v in data.values() if v.get("status") == "failed_validation")
        rows.append((f"translations {lang}", f"{done}/{total}" + (f" ({failed} failed validation)" if failed else "")))
    rows += [
        ("pipeline on sample 1", f"{_files('pipeline_on_sample1')}/7"),
        ("pipeline retry (failed judge calls)", _retries()),
        ("temporal C4 + Marathi C2 arm", f"{_files('temporal_c4', '*/sample_*.json')}/11"),
        ("k=3 self-consistency, PMMVY", f"{_files('self_consistency/PMMVY', 'sample_*.json')}/3"),
        ("k=3 pmksypdmc (silver)", f"{_files('self_consistency/_silver_pmksypdmc', 'sample_*.json')}/3"),
        ("baseline 1", f"{_files('baseline1')}/7"),
        ("gate re-validation", f"{_files('gate_revalidation', exclude=('corpus.json',))}/21"),
        ("RAG with/without retrieval", f"{_files('rag_comparison')}/4"),
    ]
    return rows


# queue item label (scripts/run_queue.py) -> progress label above
PROGRESS_OF = {"pipeline on sample 1": "pipeline on sample 1",
               "pipeline retry: failed judge calls at max_tokens=2000": "pipeline retry (failed judge calls)",
               "pipeline retry: failed judge calls, reasoning_effort=low": "pipeline retry (failed judge calls)",
               "temporal C4 (+ Marathi arm of C2)": "temporal C4 + Marathi C2 arm",
               "k=3 self-consistency (finish)": "k=3 self-consistency, PMMVY",
               "k=3 pmksypdmc (silver)": "k=3 pmksypdmc (silver)", "baseline 1": "baseline 1",
               "gate re-validation (judge on 21 candidates)": "gate re-validation",
               "RAG with/without retrieval": "RAG with/without retrieval"}


def status() -> None:
    state = _queue_state()
    pid = state.get("pid")
    alive = bool(pid) and _alive(pid)
    at, reason = harness.stop_at(), harness.stop_reason()
    print(f"queue process: {'ALIVE' if alive else 'not running'}" + (f" (pid {pid})" if pid else ""))
    if state:
        extra = state.get("until") and f", until ~{state['until']}" or state.get("reason") and f" -- {state['reason']}" or ""
        print(f"last state:    {state.get('phase')} {state.get('item', '')}{extra}  [updated {state.get('updated')}]")
    if at is None:
        print("stop time:     NOT SET -- the queue will not start")
    else:
        left = at - datetime.now()
        print(f"stop time:     {at.isoformat(sep=' ', timespec='minutes')}"
              + (f"  ({left.days}d {left.seconds // 3600}h {left.seconds % 3600 // 60}m left)" if left.total_seconds() > 0 else "  (passed)"))
    if reason:
        print(f"blocked:       {reason}")
    print(f"tokens, last 24h (rolling): {harness.tokens_spent_rolling():,} of the queue's 175,000")
    rows = dict(progress())
    order = state.get("order") or []
    if order:
        print("\nqueue order (as the running process has it) and progress:")
        current = state.get("item")
        for i, label in enumerate(order, 1):
            key = label if label.startswith("translations") else PROGRESS_OF.get(label, label)
            marker = "->" if label == current and state.get("phase") in ("running", "waiting") else "  "
            print(f" {marker} {i:>2}. {key:<32} {rows.pop(key, '?')}")
    if rows:
        print("\nprogress:" if not order else "\nnot in the queue:")
        for label, value in rows.items():
            print(f"     {label:<32} {value}")
    log = harness.control_dir() / LOG
    if log.exists():
        print(f"\nlast log lines ({log.relative_to(ROOT)}):")
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]:
            print("  " + line)


def _powershell(script: str) -> str:
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise SystemExit(f"powershell failed: {out.stderr.strip()[:800]}")
    return out.stdout.strip()


def set_review(review: str, hours_before: float) -> None:
    review_at = datetime.fromisoformat(review)
    stop = review_at - timedelta(hours=hours_before)
    harness.control_dir().mkdir(parents=True, exist_ok=True)
    (harness.control_dir() / "stop_at.txt").write_text(stop.isoformat(timespec="minutes") + "\n", encoding="utf-8")
    action = (f"New-ScheduledTaskAction -Execute '{sys.executable}' -Argument 'scripts\\queue_status.py --stop' "
              f"-WorkingDirectory '{ROOT}'")
    _powershell(
        f"$a = {action}; $t = New-ScheduledTaskTrigger -Once -At ([datetime]'{stop.isoformat(timespec='minutes')}'); "
        f"$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; "
        f"Register-ScheduledTask -TaskName '{TASK}' -Action $a -Trigger $t -Settings $s -Force | Out-Null")
    print(f"review {review_at:%Y-%m-%d %H:%M}; no experiment call starts after {stop:%Y-%m-%d %H:%M} "
          f"({hours_before:g}h before); scheduled task {TASK} stops the queue at that time")


def stop() -> None:
    harness.control_dir().mkdir(parents=True, exist_ok=True)
    (harness.control_dir() / "STOP").write_text(datetime.now().isoformat(timespec="seconds") + "\n", encoding="utf-8")
    state = _queue_state()
    pid = state.get("pid") if state.get("phase") in ("running", "waiting") else None  # not a stale, reused pid
    if pid and _alive(pid):
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"] if os.name == "nt" else ["kill", str(pid)],
                       capture_output=True)
    with (harness.control_dir() / LOG).open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat(timespec='seconds')}] STOP requested (queue_status.py --stop)"
                + (f"; pid {pid} terminated" if pid else "") + "\n")
    print("stopped; STOP file written -- nothing restarts until --allow-restart")


def start() -> None:
    state = _queue_state()
    if state.get("pid") and _alive(state["pid"]):
        raise SystemExit(f"already running (pid {state['pid']})")
    if harness.stop_at() is None or harness.stop_reason():
        raise SystemExit(f"not starting: {harness.stop_reason() or 'no stop time set (--set-review)'}")
    log = harness.control_dir() / LOG
    command = (f'cmd.exe /c "set PYTHONPATH=.&& set PYTHONIOENCODING=utf-8&& "{sys.executable}" scripts\\run_queue.py review '
               f'>> "{log}" 2>&1"')
    pid = _powershell(
        "$si = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]0}; "
        f"$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{CommandLine='{command}'; "
        f"CurrentDirectory='{ROOT}'; ProcessStartupInformation=$si}}; \"$($r.ReturnValue) $($r.ProcessId)\"")
    code, _, cmd_pid = pid.partition(" ")
    if code != "0":
        raise SystemExit(f"Win32_Process.Create returned {code}")
    print(f"started (cmd.exe pid {cmd_pid}; the queue writes its own pid to queue_state.json); log: {log.relative_to(ROOT)}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--set-review" in args:
        hours = float(next((a.split("=", 1)[1] for a in args if a.startswith("--hours-before=")), 24))
        set_review(args[args.index("--set-review") + 1], hours)
    elif "--stop" in args:
        stop()
    elif "--allow-restart" in args:
        (harness.control_dir() / "STOP").unlink(missing_ok=True)
        print("STOP file removed; set a review time with --set-review, then --start")
    elif "--start" in args:
        start()
    else:
        status()
