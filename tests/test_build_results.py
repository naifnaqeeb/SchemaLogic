"""RESULTS.md builder (item 12): embedding generated reports and the status table. Offline."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location("build_results", ROOT / "scripts" / "build_results.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_embedded_reports_lose_their_title_and_move_one_heading_level_down(tmp_path, monkeypatch):
    br = _module()
    monkeypatch.setattr(br, "RESULTS_DIR", tmp_path)
    (tmp_path / "X.md").write_text("# Title\n\n*generated*\n\n## Section\n\n| a |\n#hashtag stays\n", encoding="utf-8")
    assert br._embed("X.md") == "*generated*\n\n### Section\n\n| a |\n#hashtag stays\n"
    assert br._embed("missing.md") == "*Not generated yet.*\n"


def test_status_marks_partial_and_unrun_experiments(monkeypatch):
    br = _module()

    class Status:
        @staticmethod
        def progress():
            return [("pipeline on sample 1", "7/7"), ("pipeline retry (failed judge calls)", "0/2"),
                    ("baseline 1", "0/7"), ("k=3 self-consistency, PMMVY", "1/3"),
                    ("k=3 pmksypdmc (silver)", "0/3"), ("gate re-validation", "21/21"),
                    ("temporal C4 + Marathi C2 arm", "4/9"), ("RAG with/without retrieval", "0/4")]

    monkeypatch.setattr(br, "_script", lambda name: Status)
    table = br._status()
    assert "| Full pipeline on Baseline 3's extraction | 7/7 — complete |" in table
    assert "0/7 — **not run yet**" in table and "4/9 — **partial**" in table
