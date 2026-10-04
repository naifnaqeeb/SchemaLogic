"""Randomised property tests for the symbolic evaluator -- the safety-critical module.

Ported (and generalised) from the fuzzers the 2026-10-04 independent review of `except_scope` wrote in
its scratch space. Two properties:

1. PRESERVATION. Member scope -- the default, and every exclusion that existed before except_scope --
   behaves exactly as the evaluator did before except_scope existed: same verdict, same exception
   raised, same trace apart from the one key added at exclusion level. The oracle is a frozen,
   verbatim copy of the pre-change evaluator (tests/reference/symbolic_engine_pre_except_scope.py).

2. SOUNDNESS. The project's core safety property: a definite verdict (ELIGIBLE / INELIGIBLE) is never
   given unless EVERY way of filling in the missing facts would give that same verdict. Checked by
   brute force over all completions of a finite value domain, across every quantifier and both
   exception scopes.

Completeness -- UNDETERMINED only when the facts genuinely don't decide -- is deliberately NOT
asserted: Kleene evaluation is sound but not complete when one field feeds several predicates, and
that gap predates except_scope (the review measured it). It is counted and printed, so a regression
in it would be visible, but it isn't a failure.

Case counts are kept small enough for every run. For the full sweeps the review ran:

    SCHEMELOGIC_FUZZ_FULL=1 python -m pytest tests/test_engine_fuzz.py -q -s

(40,000 preservation cases, 30,000 for each other property). SCHEMELOGIC_FUZZ_CASES=<n> sets every
count explicitly.
"""

from __future__ import annotations

import copy
import itertools
import os
import random
from collections import Counter

import pytest

from schemelogic.evaluator import symbolic_engine as engine
from schemelogic.schema.models import Scheme
from tests.reference import symbolic_engine_pre_except_scope as reference

_FULL = os.environ.get("SCHEMELOGIC_FUZZ_FULL") == "1"
_EXPLICIT = os.environ.get("SCHEMELOGIC_FUZZ_CASES")
PRESERVATION_CASES = int(_EXPLICIT) if _EXPLICIT else (40_000 if _FULL else 2_000)
SOUNDNESS_CASES = int(_EXPLICIT) if _EXPLICIT else (30_000 if _FULL else 600)  # each enumerates completions
PROPERTY_CASES = int(_EXPLICIT) if _EXPLICIT else (30_000 if _FULL else 3_000)

FIELDS = ("a", "b", "c")
QUANTIFIERS = ("self", "some_family_member", "all_family_members", "count_family_members")
COUNT_OPS = ("<", "<=", "==", ">", ">=")


def _scheme(inclusion: dict, exclusions: list[dict]) -> dict:
    return {
        "scheme_id": "FUZZ", "unit_of_eligibility": "family", "inclusion": inclusion, "exclusions": exclusions,
        "temporal_validity": {"extracted_at": "2026-01-01"},
        "extraction_metadata": {"confidence": 1.0, "source_clause": "fuzz"},
    }


# --- 1. preservation ---------------------------------------------------------------------------

_MIXED_VALUES = (True, False, 0, 1, 2)  # mixed types on purpose: exercises comparison errors too
_MIXED_OPS = ("==", "!=", ">=", "<")


def _mixed_pred(rng: random.Random) -> dict:
    op = rng.choice(_MIXED_OPS)
    value = rng.choice((0, 1, 2)) if op in (">=", "<") else rng.choice((True, False, 1))
    return {"field": rng.choice(FIELDS), "op": op, "value": value}


def _member_scope_scheme(rng: random.Random) -> dict:
    exclusions = []
    for _ in range(rng.randint(0, 3)):
        quantifier = rng.choice(QUANTIFIERS)
        excl = {"cat": "economic", "quantifier": quantifier, **_mixed_pred(rng)}
        if rng.random() < 0.6:
            excl["except"] = _mixed_pred(rng)
            if rng.random() < 0.5:
                excl["except_scope"] = "member"  # explicit default must equal omitted default
        if quantifier == "count_family_members":
            excl["count_op"], excl["count"] = rng.choice(COUNT_OPS), rng.randint(0, 3)
        elif rng.random() < 0.2 and quantifier == "self":
            del excl["quantifier"]  # omitted quantifier must equal explicit "self"
        exclusions.append(excl)
    inclusion = {"or": [{"cat": "economic", **_mixed_pred(rng)}, {"cat": "economic", **_mixed_pred(rng)}]}
    return _scheme(inclusion, exclusions)


def _mixed_profile(rng: random.Random) -> dict:
    def member():
        return {f: rng.choice(_MIXED_VALUES) for f in FIELDS if rng.random() < 0.7}

    profile: dict = {}
    if rng.random() < 0.9:
        profile["self"] = member()
    if rng.random() < 0.8:
        profile["family_members"] = [member() for _ in range(rng.randint(0, 3))]
    return profile


def _run(module, scheme: Scheme, profile: dict):
    try:
        return module.evaluate(scheme, copy.deepcopy(profile)).to_dict()
    except Exception as exc:  # noqa: BLE001 -- the comparison IS which exception, if any
        return ("raised", type(exc).__name__)


def _without_except_scope_key(trace: dict) -> dict:
    trace = copy.deepcopy(trace)
    for excl in trace["exclusions"]:
        excl.pop("except_scope", None)
    return trace


def test_member_scope_preserves_pre_except_scope_behaviour():
    rng = random.Random(1)
    differences = []
    for _ in range(PRESERVATION_CASES):
        data, profile = _member_scope_scheme(rng), _mixed_profile(rng)
        scheme = Scheme.model_validate(data)
        before, after = _run(reference, scheme, profile), _run(engine, scheme, profile)
        if isinstance(before, tuple) or isinstance(after, tuple):
            if before != after:
                differences.append((data, profile, before, after))
            continue
        if before["verdict"] != after["verdict"] or before["trace"] != _without_except_scope_key(after["trace"]):
            differences.append((data, profile, before["verdict"], after["verdict"]))
    print(f"\n[preservation] {PRESERVATION_CASES:,} cases, {len(differences)} differences")
    assert not differences, f"member scope diverged from the pre-except_scope evaluator: {differences[:2]}"


# --- 2. soundness ------------------------------------------------------------------------------

# Completions range over (-1..3) while predicate constants are drawn from (0..2), so every predicate
# can come out either way: with a (0..2) domain `a >= 0` is always true and `a < 0` never, which
# would let an engine that GUESSES those for a missing fact pass as sound (the 2026-10-04 second
# review built exactly that mutant, and it passed).
_DOMAIN = (-1, 0, 1, 2, 3)
_CONSTANTS = (0, 1, 2)
_SOUND_OPS = ("==", "!=", ">=", "<")
_MAX_MISSING = 5  # 5**5 = 3,125 completions per case at most


def _pred(rng: random.Random, field: str | None = None) -> dict:
    return {"field": field or rng.choice(FIELDS), "op": rng.choice(_SOUND_OPS), "value": rng.choice(_CONSTANTS)}


def _inclusion(rng: random.Random, depth: int = 0) -> dict:
    if depth >= 2 or rng.random() < 0.5:
        return {"cat": "economic", **_pred(rng)}
    return {rng.choice(("and", "or")): [_inclusion(rng, depth + 1) for _ in range(rng.randint(2, 3))]}


def _exclusion(rng: random.Random, applicant_scope: bool | None = None) -> dict:
    """One random exclusion. applicant_scope=True forces an applicant-scoped exception; None lets the
    scope vary (applicant only where valid, i.e. not with quantifier self)."""
    quantifier = rng.choice(QUANTIFIERS[1:] if applicant_scope else QUANTIFIERS)
    excl = {"cat": "economic", "quantifier": quantifier, **_pred(rng)}
    if applicant_scope or rng.random() < 0.75:
        excl["except"] = _pred(rng)
        if applicant_scope or (quantifier != "self" and rng.random() < 0.6):
            excl["except_scope"] = "applicant"
    if quantifier == "count_family_members":
        excl["count_op"], excl["count"] = rng.choice(COUNT_OPS), rng.randint(0, 3)
    return excl


def _any_scope_scheme(rng: random.Random) -> dict:
    return _scheme(_inclusion(rng), [_exclusion(rng) for _ in range(rng.randint(1, 3))])


def _partial_profile(rng: random.Random, present: float = 0.75) -> dict:
    def member():
        return {f: rng.choice(_DOMAIN) for f in FIELDS if rng.random() < present}

    profile: dict = {}
    if rng.random() < 0.9:
        profile["self"] = member()
    if rng.random() < 0.85:
        profile["family_members"] = [member() for _ in range(rng.randint(0, 3))]
    return profile


def _completions(profile: dict) -> list[dict] | None:
    """Every way of filling the profile's missing facts from _DOMAIN, or None if there are too many.
    A missing "self" or "family_members" key is completed as an empty record / empty family."""
    full = copy.deepcopy(profile)
    full.setdefault("self", {})
    full.setdefault("family_members", [])
    records = [full["self"], *full["family_members"]]
    slots = [(i, f) for i, record in enumerate(records) for f in FIELDS if f not in record]
    if len(slots) > _MAX_MISSING:
        return None
    out = []
    for values in itertools.product(_DOMAIN, repeat=len(slots)):
        filled = copy.deepcopy(full)
        filled_records = [filled["self"], *filled["family_members"]]
        for (i, f), v in zip(slots, values):
            filled_records[i][f] = v
        out.append(filled)
    return out


def test_definite_verdicts_are_sound_over_every_completion_of_missing_facts():
    rng = random.Random(7)
    stats: Counter = Counter()
    unsound = []
    for _ in range(SOUNDNESS_CASES):
        data, profile = _any_scope_scheme(rng), _partial_profile(rng)
        scheme = Scheme.model_validate(data)
        completions = _completions(profile)
        if completions is None:
            stats["skipped (too many missing facts)"] += 1
            continue
        verdict = engine.evaluate(scheme, profile).verdict
        outcomes = {engine.evaluate(scheme, c).verdict for c in completions}
        scope = "applicant" if any(e.get("except_scope") == "applicant" for e in data["exclusions"]) else "member"
        if verdict != engine.Verdict.UNDETERMINED:
            if outcomes != {verdict}:
                unsound.append((data, profile, verdict, outcomes))
            stats[f"{scope}: definite, sound"] += 1
        elif len(outcomes) == 1:
            stats[f"{scope}: undetermined although decided (incomplete, not asserted)"] += 1
        else:
            stats[f"{scope}: undetermined, genuinely open"] += 1
    print(f"\n[soundness] {SOUNDNESS_CASES:,} cases, {len(unsound)} unsound")
    for key in sorted(stats):
        print(f"  {key}: {stats[key]:,}")
    assert not unsound, f"definite verdict contradicted by a completion of the missing facts: {unsound[:2]}"


# --- 3. intended semantics, stated independently -------------------------------------------------
# The soundness check judges completions with the engine itself, so an engine that is consistently
# WRONG -- say, reading the applicant's waiver off family_members[0] -- passes it. This is a separate,
# deliberately naive two-valued statement of what the rules mean, compared on complete profiles.

_TWO_VALUED_OPS = {"==": lambda a, b: a == b, "!=": lambda a, b: a != b,
                   ">=": lambda a, b: a >= b, "<": lambda a, b: a < b}
_COUNT_CMP = {"<": lambda n, k: n < k, "<=": lambda n, k: n <= k, "==": lambda n, k: n == k,
              ">": lambda n, k: n > k, ">=": lambda n, k: n >= k}


def _holds(pred: dict, record: dict) -> bool:
    return _TWO_VALUED_OPS[pred["op"]](record[pred["field"]], pred["value"])


def _reference_inclusion(node: dict, record: dict) -> bool:
    if "and" in node:
        return all(_reference_inclusion(c, record) for c in node["and"])
    if "or" in node:
        return any(_reference_inclusion(c, record) for c in node["or"])
    return _holds(node, record)


def _reference_excluded(excl: dict, profile: dict) -> bool:
    """A rule looks at the applicant, or at the applicant and the family: does anyone / everyone /
    how many of them meet the condition. A member-scoped exception exempts the person it holds for;
    an applicant-scoped exception waives the whole rule when it holds for the applicant."""
    applicant, family = profile["self"], profile["family_members"]
    quantifier = excl.get("quantifier", "self")
    people = [applicant] if quantifier == "self" else [applicant, *family]
    exception, scope = excl.get("except"), excl.get("except_scope", "member")

    def counts(person: dict) -> bool:
        return _holds(excl, person) and not (exception and scope == "member" and _holds(exception, person))

    hits = [counts(p) for p in people]
    if quantifier == "all_family_members":
        fires = all(hits)
    elif quantifier == "count_family_members":
        fires = _COUNT_CMP[excl["count_op"]](sum(hits), excl["count"])
    else:
        fires = any(hits)
    return fires and not (exception and scope == "applicant" and _holds(exception, applicant))


def _reference_verdict(data: dict, profile: dict) -> engine.Verdict:
    excluded = any(_reference_excluded(e, profile) for e in data["exclusions"])
    eligible = _reference_inclusion(data["inclusion"], profile["self"]) and not excluded
    return engine.Verdict.ELIGIBLE if eligible else engine.Verdict.INELIGIBLE


def test_engine_matches_an_independent_two_valued_reference_on_complete_profiles():
    rng = random.Random(13)
    mismatches = []
    for _ in range(PROPERTY_CASES):
        data, profile = _any_scope_scheme(rng), _partial_profile(rng, present=1.0)
        profile.setdefault("self", {f: rng.choice(_DOMAIN) for f in FIELDS})
        profile.setdefault("family_members", [])
        got = engine.evaluate(Scheme.model_validate(data), profile).verdict
        want = _reference_verdict(data, profile)
        if got != want:
            mismatches.append((data, profile, got, want))
    print(f"\n[reference] {PROPERTY_CASES:,} complete profiles, {len(mismatches)} mismatches")
    assert not mismatches, f"engine disagrees with the two-valued reference: {mismatches[:2]}"


# --- 4. a waiver never makes anyone worse off ---------------------------------------------------

_RANK = {engine.Verdict.INELIGIBLE: 0, engine.Verdict.UNDETERMINED: 1, engine.Verdict.ELIGIBLE: 2}


def _without_exceptions(data: dict) -> dict:
    data = copy.deepcopy(data)
    for excl in data["exclusions"]:
        excl.pop("except", None)
        excl.pop("except_scope", None)
    return data


def test_applicant_scoped_exception_never_makes_a_verdict_worse_than_no_exception():
    """The defining property of a waiver, against the no-exception baseline and with missing facts:
    never ELIGIBLE -> UNDETERMINED/INELIGIBLE, never UNDETERMINED -> INELIGIBLE."""
    rng = random.Random(17)
    worse = []
    for _ in range(PROPERTY_CASES):
        data = _scheme(_inclusion(rng), [_exclusion(rng, applicant_scope=True) for _ in range(rng.randint(1, 2))])
        profile = _partial_profile(rng)
        with_exception = engine.evaluate(Scheme.model_validate(data), profile).verdict
        baseline = engine.evaluate(Scheme.model_validate(_without_exceptions(data)), profile).verdict
        if _RANK[with_exception] < _RANK[baseline]:
            worse.append((data, profile, baseline, with_exception))
    print(f"\n[no worse off] {PROPERTY_CASES:,} cases, {len(worse)} made worse by the exception")
    assert not worse, worse[:2]


# --- 5. completeness where it is achievable ------------------------------------------------------


@pytest.mark.parametrize("quantifier", ["some_family_member", "all_family_members", "count_family_members"])
@pytest.mark.parametrize("seed", [11, 23])
def test_applicant_scope_is_complete_when_condition_exception_and_inclusion_use_disjoint_fields(quantifier, seed):
    """The incompleteness the first review found -- count quantifiers under applicant scope treating the
    members' shared waiver as independent unknowns -- is fixed. With the exclusion, its exception and
    the inclusion on DISJOINT fields (so the pre-existing shared-field gap can't occur), every
    undetermined verdict must be genuinely open, for every family quantifier."""
    rng = random.Random(seed)
    checked = 0
    for _ in range(300 if not _FULL else 3_000):
        excl = {"cat": "economic", "quantifier": quantifier, **_pred(rng, "a"),
                "except": _pred(rng, "b"), "except_scope": "applicant"}
        if quantifier == "count_family_members":
            excl.update(count_op=rng.choice(COUNT_OPS), count=rng.randint(0, 3))
        scheme = Scheme.model_validate(_scheme({"cat": "economic", "field": "c", "op": "==", "value": 1}, [excl]))
        profile = _partial_profile(rng)
        profile.setdefault("self", {})["c"] = 1  # inclusion met: the verdict turns on the exclusion
        completions = _completions(profile)
        if completions is None:
            continue
        if engine.evaluate(scheme, profile).verdict == engine.Verdict.UNDETERMINED:
            checked += 1
            assert len({engine.evaluate(scheme, c).verdict for c in completions}) > 1, (excl, profile)
    assert checked > 20  # the property was actually exercised
