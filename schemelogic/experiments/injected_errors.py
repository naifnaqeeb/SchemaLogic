"""A SYNTHETIC injected-error corpus from the frozen gold -- final-push item 6 (gate re-validation).

Every error is a deterministic, labelled mutation of one gold predicate, of one of six kinds:

  dropped_predicate      an inclusion leaf or an exclusion removed
  flipped_operator       > <-> >=, < <-> <=, == <-> != (booleans: == True <-> == False)
  wrong_threshold        a numeric value moved off its threshold (x1.5, or +1 for small integers)
  wrong_quantifier       an exclusion's quantifier changed (self <-> some_family_member)
  wrong_exception_scope  an exception removed, or its scope switched member <-> applicant where valid
  fabricated_supersedes  a temporal_validity.supersedes block invented for a predicate the source
                         never says was amended

Errors are grouped a few per mutated scheme (never two on the same predicate), so one judge call can
be scored against several labelled errors. These are synthetic errors on gold, not errors a real
extraction made -- results on them say what the gate CAN catch, not how often real errors occur.
"""

from __future__ import annotations

import copy
import random
from dataclasses import asdict, dataclass
from typing import Any

from schemelogic.schema.models import Scheme

KINDS = ("dropped_predicate", "flipped_operator", "wrong_threshold", "wrong_quantifier",
         "wrong_exception_scope", "fabricated_supersedes")
_FLIP = {">": ">=", ">=": ">", "<": "<=", "<=": "<", "==": "!=", "!=": "=="}


@dataclass
class InjectedError:
    error_id: str
    scheme_id: str
    kind: str
    location: str  # e.g. "inclusion.and[2].or[1]", "exclusions[3]", "exclusions[3].except", "temporal_validity"
    before: Any
    after: Any
    description: str


def _leaves(node: dict, path: str):
    for key in ("and", "or"):
        if key in node:
            for i, child in enumerate(node[key]):
                yield from _leaves(child, f"{path}.{key}[{i}]")
            return
    yield path, node


def _get(data: dict, location: str) -> dict:
    node: Any = data
    for part in location.replace("]", "").split("."):
        if "[" in part:
            name, index = part.split("[")
            node = node[name][int(index)]
        else:
            node = node[part]
    return node


def candidates(gold: Scheme) -> dict[str, list[tuple[str, str]]]:
    """(location, kind) pairs each kind can be applied to in this scheme."""
    data = gold.model_dump(mode="json", by_alias=True)
    out: dict[str, list[tuple[str, str]]] = {k: [] for k in KINDS}
    inclusion = list(_leaves(data["inclusion"], "inclusion"))
    for loc, leaf in inclusion:
        if len(inclusion) > 1:
            out["dropped_predicate"].append((loc, "dropped_predicate"))
        if leaf["op"] in _FLIP or isinstance(leaf["value"], bool):
            out["flipped_operator"].append((loc, "flipped_operator"))
        if isinstance(leaf["value"], (int, float)) and not isinstance(leaf["value"], bool):
            out["wrong_threshold"].append((loc, "wrong_threshold"))
    for i, e in enumerate(data.get("exclusions", [])):
        loc = f"exclusions[{i}]"
        out["dropped_predicate"].append((loc, "dropped_predicate"))
        out["flipped_operator"].append((loc, "flipped_operator"))
        if isinstance(e["value"], (int, float)) and not isinstance(e["value"], bool):
            out["wrong_threshold"].append((loc, "wrong_threshold"))
        if e.get("quantifier", "self") in ("self", "some_family_member") and not (e.get("except_scope") == "applicant"):
            out["wrong_quantifier"].append((loc, "wrong_quantifier"))
        if e.get("except"):
            out["wrong_exception_scope"].append((f"{loc}.except", "wrong_exception_scope"))
    if not (data.get("temporal_validity") or {}).get("supersedes"):
        out["fabricated_supersedes"].append(("temporal_validity", "fabricated_supersedes"))
    return out


def apply(data: dict, error: InjectedError) -> None:
    """Apply one mutation in place (locations are resolved before any removal, so callers apply
    removals last -- see build_corpus)."""
    kind, loc = error.kind, error.location
    if kind == "dropped_predicate":
        parent_loc, index = loc.rsplit("[", 1)
        parent = _get(data, parent_loc.rsplit(".", 1)[0]) if "." in parent_loc else data
        key = parent_loc.rsplit(".", 1)[-1]
        parent[key][int(index.rstrip("]"))] = None  # tombstone, swept after all mutations
    elif kind in ("flipped_operator", "wrong_threshold", "wrong_quantifier"):
        node = _get(data, loc)
        node.update(error.after)
    elif kind == "wrong_exception_scope":
        node = _get(data, loc.rsplit(".", 1)[0])
        if error.after is None:
            node.pop("except", None)
            node.pop("except_scope", None)
        else:
            node["except_scope"] = error.after
    elif kind == "fabricated_supersedes":
        data["temporal_validity"]["supersedes"] = error.after


def _sweep(node: Any) -> Any:
    if isinstance(node, dict):
        for key in ("and", "or"):
            if key in node:
                node[key] = [_sweep(c) for c in node[key] if c is not None]
        return node
    return node


def _mutation(gold_data: dict, sid: str, kind: str, loc: str, n: int, rng: random.Random) -> InjectedError:
    eid = f"{sid}#{n:02d}"
    if kind == "dropped_predicate":
        node = _get(gold_data, loc)
        return InjectedError(eid, sid, kind, loc, {k: node[k] for k in ("field", "op", "value")}, None,
                             f"removed {node['field']} {node['op']} {node['value']!r}")
    if kind == "flipped_operator":
        node = _get(gold_data, loc)
        if isinstance(node["value"], bool) and node["op"] == "==":
            after = {"value": not node["value"]}
        else:
            after = {"op": _FLIP[node["op"]]}
        return InjectedError(eid, sid, kind, loc, {"op": node["op"], "value": node["value"]}, after,
                             f"{node['field']}: {node['op']} {node['value']!r} -> {after}")
    if kind == "wrong_threshold":
        node = _get(gold_data, loc)
        v = node["value"]
        new = v + 1 if isinstance(v, int) and abs(v) < 20 else (round(v * 1.5) if isinstance(v, int) else round(v * 1.5, 2))
        return InjectedError(eid, sid, kind, loc, {"value": v}, {"value": new}, f"{node['field']}: {v} -> {new}")
    if kind == "wrong_quantifier":
        node = _get(gold_data, loc)
        q = node.get("quantifier", "self")
        new = "some_family_member" if q == "self" else "self"
        return InjectedError(eid, sid, kind, loc, {"quantifier": q}, {"quantifier": new}, f"{node['field']}: {q} -> {new}")
    if kind == "wrong_exception_scope":
        excl = _get(gold_data, loc.rsplit(".", 1)[0])
        scope = excl.get("except_scope", "member")
        switch_ok = excl.get("quantifier", "self") != "self" and excl.get("quantifier") != "count_family_members"
        after = ("applicant" if scope == "member" else "member") if switch_ok and rng.random() < 0.5 else None
        what = f"scope {scope} -> {after}" if after else "exception removed"
        return InjectedError(eid, sid, kind, loc, {"except": excl["except"], "except_scope": scope}, after,
                             f"{excl['field']}: {what}")
    if kind == "fabricated_supersedes":
        leaves = [leaf for _, leaf in _leaves(gold_data["inclusion"], "inclusion")]
        target = rng.choice(leaves)
        v = target["value"]
        retired = not v if isinstance(v, bool) else (round(v * 0.8, 2) if isinstance(v, (int, float)) else v)
        after = {"rule_version": "pre_amendment", "retired_predicate": {"field": target["field"], "op": target["op"], "value": retired},
                 "amendment_source": "an amendment that changed this criterion"}
        return InjectedError(eid, sid, kind, "temporal_validity", None, after,
                             f"invented: {target['field']} {target['op']} {retired!r} retired by an amendment")
    raise ValueError(kind)


def build_corpus(golds: dict[str, Scheme], n_errors: int = 30, per_scheme: int = 3, seed: int = 20261005
                 ) -> list[dict]:
    """Up to `per_scheme` errors per mutated scheme, kinds balanced across the corpus, deterministic.
    Returns [{"variant_id", "scheme_id", "errors": [InjectedError...], "scheme": mutated dump}]."""
    rng = random.Random(seed)
    pools = {sid: candidates(g) for sid, g in golds.items()}
    used: dict[str, set[str]] = {sid: set() for sid in golds}
    errors: list[InjectedError] = []
    counter = 0
    kind_cycle = list(KINDS)
    while len(errors) < n_errors:
        progressed = False
        for kind in kind_cycle:
            if len(errors) >= n_errors:
                break
            options = [(sid, loc) for sid in sorted(pools) for loc, _ in pools[sid][kind]
                       if loc not in used[sid] and not (kind == "fabricated_supersedes" and "temporal_validity" in used[sid])]
            if not options:
                continue
            # balance across schemes: draw from the schemes with the fewest errors so far
            fewest = min(sum(e.scheme_id == s for e in errors) for s, _ in options)
            options = [(s, loc) for s, loc in options if sum(e.scheme_id == s for e in errors) == fewest]
            sid, loc = rng.choice(options)
            counter += 1
            errors.append(_mutation(golds[sid].model_dump(mode="json", by_alias=True), sid, kind, loc, counter, rng))
            used[sid].add(loc)
            progressed = True
        if not progressed:
            break

    variants: list[dict] = []
    by_scheme: dict[str, list[InjectedError]] = {}
    for e in errors:
        by_scheme.setdefault(e.scheme_id, []).append(e)
    def base(e: InjectedError) -> str:
        return e.location.split(".except")[0]

    for sid, errs in sorted(by_scheme.items()):
        groups: list[list[InjectedError]] = []
        for e in errs:  # first group with room and no error on the same predicate
            home = next((g for g in groups if len(g) < per_scheme and all(base(o) != base(e) for o in g)), None)
            if home is None:
                groups.append(home := [])
            home.append(e)
        for n, group in enumerate(groups, 1):
            data = copy.deepcopy(golds[sid].model_dump(mode="json", by_alias=True))
            # removals last, so earlier locations stay valid; dropped exclusions swept by index
            for e in sorted(group, key=lambda e: e.kind == "dropped_predicate"):
                apply(data, e)
            data["exclusions"] = [x for x in data.get("exclusions", []) if x is not None]
            _sweep(data["inclusion"])
            scheme = Scheme.model_validate(data)  # every variant must still be a valid scheme
            variants.append({"variant_id": f"{sid}~{n}", "scheme_id": sid,
                             "errors": [asdict(e) for e in group],
                             "scheme": scheme.model_dump(mode="json", by_alias=True)})
    return variants
