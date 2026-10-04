"""Pydantic models for the extended JSON-Logic eligibility schema (Section 2 of IMPLEMENTATION_PLAN.md)."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Annotated, Any, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PredicateCategory(str, Enum):
    """Controlled vocabulary for predicate `cat` tags. Drives the C3 failure taxonomy — don't let this drift."""

    CITIZENSHIP = "citizenship"
    DEMOGRAPHIC = "demographic"
    OCCUPATION = "occupation"
    ECONOMIC = "economic"
    POLITICAL = "political"
    PROFESSIONAL = "professional"
    INSTITUTIONAL = "institutional"
    FAMILY_UNIT = "family_unit"
    TEMPORAL = "temporal"
    CROSS_SCHEME = "cross_scheme"
    VACUOUS = "vacuous"
    OTHER = "other"


class Operator(str, Enum):
    EQ = "=="
    NE = "!="
    LT = "<"
    LTE = "<="
    GT = ">"
    GTE = ">="
    IN = "in"
    NOT_IN = "not_in"


class Quantifier(str, Enum):
    SELF = "self"
    SOME_FAMILY_MEMBER = "some_family_member"
    ALL_FAMILY_MEMBERS = "all_family_members"
    COUNT_FAMILY_MEMBERS = "count_family_members"


# Whose facts an exclusion's `except` clause is read from.
#
# MEMBER (the default, and every exclusion's behaviour before 2026-10-03): the exception is checked
# on the same member who triggered the exclusion. Right for exemptions that are a property of that
# person -- PM-KISAN's "government employees, EXCEPT Group D staff" exempts the Group D employee.
#
# APPLICANT: the exception is read once, from the applicant's own record (profile["self"]), for
# every member. Needed when the exemption is a property of the application route rather than of the
# member who tripped the exclusion. AB-PMJAY's 70+ route forced it: the NHA covers citizens aged 70+
# "irrespective of their socio-economic status", so an income-tax-paying son must not block his
# 75-year-old father's coverage. A member-scoped exception reads the 70+ fact off the son, finds
# nothing, and yields "undetermined" -- and in a household with no 70+ member at all, turns a
# correct "ineligible" into "undetermined" too. Logically the route needs
# `eligible = route OR (others AND NOT excluded)`: each exclusion carries `AND NOT route`, where
# `route` is a fact about the applicant's household. See docs/GOLD_AUDIT_2026-10-03.md.
#
# Kept as a comment, not a docstring, deliberately: Pydantic embeds class docstrings into
# model_json_schema(), which extraction/extractor.py sends to the LLM on every core call. As a
# docstring this rationale cost ~436 tokens per extraction on an account where the completion
# budget is already the main failure mode (measured 2026-10-03).
class ExceptScope(str, Enum):
    """Whose record an exclusion's `except` clause is read from: the triggering member, or the applicant."""

    MEMBER = "member"
    APPLICANT = "applicant"


class CountOperator(str, Enum):
    """Comparison used against a family-member count (Phase 0.5 counting-quantifier extension)."""

    LT = "<"
    LTE = "<="
    EQ = "=="
    GT = ">"
    GTE = ">="


class SimplePredicate(BaseModel):
    """A leaf condition without a category tag — used for `except` clauses (Section 2.2 example
    omits `cat` on the exception sub-predicate; it inherits taxonomy relevance from its parent)."""

    model_config = ConfigDict(extra="forbid")

    field: str
    op: Operator
    value: Any
    ontology_proposed: bool = False
    """Set true when `field` is NOT in schema.field_ontology's canonical vocabulary and the
    extractor is proposing it as a genuinely new field, rather than silently inventing an ad hoc
    name. False (default) means the field is either a canonical ontology field or was produced
    outside the ontology-aware extraction path (e.g. hand-authored gold/test fixtures)."""


class Predicate(SimplePredicate):
    """A single leaf condition: field <op> value, tagged with its failure-taxonomy category."""

    cat: PredicateCategory


class AndNode(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    and_: list["LogicNode"] = Field(alias="and")


class OrNode(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    or_: list["LogicNode"] = Field(alias="or")


LogicNode = Annotated[Union[AndNode, OrNode, Predicate], Field(union_mode="smart")]

AndNode.model_rebuild()
OrNode.model_rebuild()


class Exclusion(Predicate):
    """A predicate that disqualifies, optionally scoped to family members and carrying an exception.

    `field`/`op`/`value` (inherited from Predicate) is the per-member condition. For
    `quantifier == count_family_members`, that condition is what's being counted, and
    `count_op`/`count` express the threshold that triggers the exclusion (e.g. "count of family
    members already receiving the benefit >= 2").
    """

    quantifier: Quantifier = Quantifier.SELF
    except_: SimplePredicate | None = Field(default=None, alias="except")
    except_scope: ExceptScope = ExceptScope.MEMBER
    count_op: CountOperator | None = None
    count: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _validate_except_scope(self) -> "Exclusion":
        # An explicit "member" with no exception is accepted: it is the default, and says nothing.
        if self.except_scope != ExceptScope.MEMBER and self.except_ is None:
            raise ValueError(f"except_scope '{self.except_scope.value}' requires an `except` clause")
        if self.except_scope == ExceptScope.APPLICANT and self.quantifier == Quantifier.SELF:
            # A self-quantified exclusion only ever reads the applicant, so applicant scope changes
            # nothing -- accepting it would only hide an authoring or extraction mistake.
            raise ValueError("except_scope 'applicant' has no effect with quantifier 'self'; use 'member'")
        if (
            self.except_ is not None and self.except_scope == ExceptScope.MEMBER
            and self.count_op in (CountOperator.LT, CountOperator.LTE, CountOperator.EQ)
        ):
            # A member-scoped exception exempts members from the count, which LOWERS it -- under
            # "<", "<=" or "==" that can make the exclusion fire because of the exception (second
            # independent review, 2026-10-04, finding 6).
            raise ValueError(
                f"a member-scoped `except` cannot be combined with count_op '{self.count_op.value}': "
                "exempting a member lowers the count, so the exception could trigger the exclusion"
            )
        return self

    @model_validator(mode="after")
    def _validate_count_fields(self) -> "Exclusion":
        is_count_quantifier = self.quantifier == Quantifier.COUNT_FAMILY_MEMBERS
        count_fields_set = self.count_op is not None or self.count is not None
        if is_count_quantifier and not (self.count_op is not None and self.count is not None):
            raise ValueError(
                "count_op and count are both required when quantifier == count_family_members"
            )
        if not is_count_quantifier and count_fields_set:
            raise ValueError(
                "count_op/count must not be set unless quantifier == count_family_members"
            )
        return self


class Supersedes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_version: str
    retired_predicate: dict[str, Any]
    amendment_source: str


class TemporalValidity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid_from: date | None = None
    """When the rules took legal effect, or None when the source document genuinely doesn't say.

    Optional since 2026-09-15. Every hand-annotated gold scheme sets a real date (they're
    annotated from primary notifications, which carry one), so nothing about the gold path or the
    Phase 3 numbers changes. It's the myScheme-scraped silver records that frequently state no
    effective date at all: making this required meant a live AI-Checked extraction whose
    eligibility logic was completely sound got thrown away over absent DATE METADATA, dropping the
    citizen to the description-only fallback (measured 2026-09-15 on dmrnicmasii, whose extraction
    recovered a correct nested-OR inclusion tree and then failed validation on
    `valid_from: null`).

    None means "the source document does not state one" -- deliberately not filled in with
    extracted_at or today's date, which would assert an effective date the document never gave.
    Nothing in the evaluator reads this field; eligibility never depends on it."""

    valid_to: date | None = None
    extracted_at: date
    supersedes: Supersedes | None = None

    @model_validator(mode="after")
    def _valid_to_after_valid_from(self) -> "TemporalValidity":
        if self.valid_to is not None and self.valid_from is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not be before valid_from")
        return self


class ExtractionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confidence: float = Field(ge=0.0, le=1.0)
    source_clause: str
    flagged_for_review: bool = False


class UnitOfEligibility(str, Enum):
    INDIVIDUAL = "individual"
    FAMILY = "family"


class Scheme(BaseModel):
    """Root schema for one scheme's eligibility logic (one rule version)."""

    model_config = ConfigDict(extra="forbid")

    scheme_id: str
    unit_of_eligibility: UnitOfEligibility
    inclusion: LogicNode
    exclusions: list[Exclusion] = Field(default_factory=list)
    temporal_validity: TemporalValidity
    operational_requirements: list[str] = Field(default_factory=list)
    extraction_metadata: ExtractionMetadata


def dump_gold_json(scheme: Scheme) -> str:
    """The one canonical serialization for gold scheme files (data/gold/*.json).

    Fields at their default are omitted (`exclude_defaults=True`), so adding a defaulted field to
    the schema -- as `except_scope` was on 2026-10-03 -- doesn't rewrite every gold file, and a field
    appears only where it says something: `except_scope` shows up only on the exceptions that are
    genuinely applicant-scoped. The cost is explicitness: an absent `quantifier` means "self", an
    absent `flagged_for_review` means false. tests/test_gold_schemes.py checks every gold file is
    byte-identical to this output, so a hand edit that isn't canonical fails the suite rather than
    accumulating drift (`PYTHONPATH=. python scripts/audit_gold.py format` rewrites them)."""
    import json

    data = scheme.model_dump(mode="json", by_alias=True, exclude_defaults=True)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
