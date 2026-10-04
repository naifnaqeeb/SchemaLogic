"""scripts/run_batch_report.py -- offline aggregate report against frozen gold."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("run_batch_report", ROOT / "scripts" / "run_batch_report.py")
report_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report_module)


def test_report_covers_every_scheme_and_configuration_with_caveats_and_superseded_claims():
    report = report_module.build()
    assert report["gold_tag"] == "gold-v2"
    assert any("ONTOLOGY CONTAMINATION" in c for c in report["caveats"])
    assert len(report["superseded_claims"]) >= 15
    assert set(report["configurations"]) >= {"phase3_pipeline", "baseline3_extraction_only", "baseline1_flat"}
    phase3 = report["configurations"]["phase3_pipeline"]
    assert sorted([*phase3["per_scheme"], *phase3["absent"]]) == report_module.harness.gold_scheme_ids()
    # the recorded figure (audit doc s7.8): AB-PMJAY's gate-approved draft against current gold
    assert round(phase3["per_scheme"]["AB-PMJAY"]["structural_f1"]["f1"], 3) == 0.692
    assert set(report["baseline2"]) == set(report_module.harness.gold_scheme_ids())


def test_markdown_renders_absent_configurations_honestly():
    md = report_module.markdown(report_module.build())
    assert "## Caveats — read first" in md and "do not cite the left column" in md
