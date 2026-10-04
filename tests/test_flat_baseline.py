"""Baseline 1 -- flat attribute extraction (evaluation/flat_baseline.py). No network: faked client."""

from __future__ import annotations

import json
from types import SimpleNamespace

from schemelogic.evaluation import flat_baseline
from schemelogic.evaluator.symbolic_engine import Verdict, evaluate
from schemelogic.extraction.extractor import ExtractionFailure
from schemelogic.schema.models import Scheme

FLAT = {"scheme_id": "X", "criteria": [
    {"field": "age", "op": ">=", "value": 60, "cat": "demographic", "kind": "required"},
    {"field": "is_bpl_household", "op": "==", "value": True, "cat": "economic", "kind": "required"},
    {"field": "is_govt_employee", "op": "==", "value": True, "cat": "occupation", "kind": "disqualifying"},
]}


class FakeClient:
    def __init__(self, content):
        self.content, self.calls = content, []
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=json.dumps(self.content))
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15))


def test_a_flat_list_becomes_and_of_required_plus_self_disqualifiers():
    scheme = flat_baseline.to_scheme(FLAT)
    assert isinstance(scheme, Scheme)
    assert [p.field for p in scheme.inclusion.and_] == ["age", "is_bpl_household"]
    assert [(e.field, e.quantifier.value, e.except_) for e in scheme.exclusions] == [("is_govt_employee", "self", None)]
    ok = {"self": {"age": 65, "is_bpl_household": True, "is_govt_employee": False}}
    assert evaluate(scheme, ok).verdict == Verdict.ELIGIBLE


def test_alternatives_cannot_be_expressed_so_both_become_required():
    """'BPL OR an AIDS widow' read flat is 'BPL AND an AIDS widow' -- the limitation being measured."""
    flat = {"scheme_id": "X", "criteria": [
        {"field": "is_bpl_household", "op": "==", "value": True, "kind": "required"},
        {"field": "is_widow_suffering_from_aids", "op": "==", "value": True, "kind": "required"}]}
    scheme = flat_baseline.to_scheme(flat)
    assert evaluate(scheme, {"self": {"is_bpl_household": True, "is_widow_suffering_from_aids": False}}).verdict == Verdict.INELIGIBLE


def test_no_required_condition_is_a_failure_not_a_scheme():
    assert isinstance(flat_baseline.to_scheme({"scheme_id": "X", "criteria": []}), ExtractionFailure)


def test_extract_flat_makes_one_structured_call_and_reports_usage():
    client, usage = FakeClient(FLAT), []
    scheme, raw = flat_baseline.extract_flat("doc", client=client, usage_sink=usage.append)
    assert isinstance(scheme, Scheme) and raw == FLAT
    assert len(client.calls) == 1 and client.calls[0]["response_format"]["json_schema"]["name"] == "flat_eligibility_conditions"
    assert usage[0]["total_tokens"] == 15
