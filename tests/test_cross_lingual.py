"""Cross-lingual case study (C2) analysis -- final-push item 10. Offline, on stub samples."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from schemelogic.experiments import harness

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location("analyze_cross_lingual", ROOT / "scripts" / "analyze_cross_lingual.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_language_pairs_are_compared_against_the_same_language_noise_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "EXPERIMENTS_DIR", tmp_path)
    c2 = _module()
    gold = harness.frozen_gold("MH-LADKI-BAHIN").model_dump(mode="json", by_alias=True)
    for lang, (_, rel) in c2.ARMS.items():
        (tmp_path / rel).mkdir(parents=True)
        (tmp_path / rel / "sample_1.json").write_text(json.dumps({"draft_extraction": gold}), encoding="utf-8")
        (tmp_path / rel / "sample_2.json").write_text(json.dumps({"draft_extraction": gold}), encoding="utf-8")
    (tmp_path / c2.ARMS["en"][1] / "sample_3.json").write_text(json.dumps({"failure": {"reason": "x"}}), encoding="utf-8")

    a = c2.analyze()
    assert [d["status"] for d in a["per_draft"]].count("extraction failed") == 1
    assert all(d["agreement_rate"] == 1.0 for d in a["per_draft"] if d["status"] == "ok")
    assert a["pairwise_by_kind"] == {"en-en": {"pairs": 1, "mean_agreement": 1.0}, "mr-mr": {"pairs": 1, "mean_agreement": 1.0},
                                     "mr-en": {"pairs": 4, "mean_agreement": 1.0}}
    assert "| mr-en | 4 | 100.0% |" in c2.markdown(a)
