"""The synthetic injected-error corpus (final-push item 6)."""

from __future__ import annotations

from collections import Counter

import pytest

from schemelogic.evaluation.structural_f1 import flatten_scheme
from schemelogic.experiments import harness, injected_errors as ie
from schemelogic.schema.models import Scheme

GOLDS = {s: harness.frozen_gold(s) for s in harness.gold_scheme_ids()}


@pytest.fixture(scope="module")
def corpus():
    return ie.build_corpus(GOLDS)


def test_corpus_is_deterministic_and_about_thirty_errors(corpus):
    assert corpus == ie.build_corpus(GOLDS)
    errors = [e for v in corpus for e in v["errors"]]
    assert len(errors) == 30
    assert set(Counter(e["kind"] for e in errors)) == set(ie.KINDS)
    assert max(Counter(e["scheme_id"] for e in errors).values()) - min(Counter(e["scheme_id"] for e in errors).values()) <= 1


def test_every_variant_is_a_valid_scheme_that_differs_from_its_gold(corpus):
    for v in corpus:
        mutated = Scheme.model_validate(v["scheme"])
        gold = GOLDS[v["scheme_id"]]
        changed_rules = sorted(p.match_key() for p in flatten_scheme(mutated)) != sorted(p.match_key() for p in flatten_scheme(gold))
        changed_supersedes = mutated.temporal_validity.supersedes != gold.temporal_validity.supersedes
        assert changed_rules or changed_supersedes, v["variant_id"]


def test_no_variant_mutates_one_predicate_twice(corpus):
    for v in corpus:
        bases = [e["location"].split(".except")[0] for e in v["errors"]]
        assert len(bases) == len(set(bases)), v["variant_id"]


def test_errors_are_labelled_with_before_and_after(corpus):
    for e in (e for v in corpus for e in v["errors"]):
        assert e["description"] and e["location"] and e["kind"] in ie.KINDS
        assert e["before"] is not None or e["kind"] == "fabricated_supersedes"
