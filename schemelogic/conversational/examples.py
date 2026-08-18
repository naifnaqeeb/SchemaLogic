"""Pre-loaded example profiles for the chat UI's quick-start buttons (Phase 8, Step 4). All on
PM-KISAN, since it's the scheme with the richest already-validated except-clause behavior
(Group D/Class IV/MTS carve-outs on the govt-employee and pensioner exclusions) — see
tests/fixtures.py for the underlying gold scheme these mirror.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExampleProfile:
    label: str
    scheme_id: str
    description: str
    profile: dict[str, Any]


_PM_KISAN_BASE_SELF: dict[str, Any] = {
    "owns_cultivable_land_in_records": True,
    "is_institutional_landholder": False,
    "paid_income_tax_last_assessment_year": False,
    "is_serving_or_retired_govt_employee": False,
    "is_group_d_class_iv_or_mts": False,
    "monthly_pension_inr": 0,
    "holds_constitutional_or_political_post": False,
    "holds_elected_or_nominated_govt_post": False,
    "is_practicing_registered_professional": False,
    "is_nri_per_income_tax_act_1961": False,
}

EXAMPLES: list[ExampleProfile] = [
    ExampleProfile(
        label="Group D exception case",
        scheme_id="PM-KISAN",
        description=(
            "A government employee, but Group D / Class IV / MTS — the standard except-clause "
            "carve-out on PM-KISAN's govt-employee exclusion. Everything else is known, so this "
            "should resolve immediately to ELIGIBLE despite is_serving_or_retired_govt_employee "
            "being true, because the except clause fires."
        ),
        profile={
            "self": {
                **_PM_KISAN_BASE_SELF,
                "is_indian_citizen": True,
                "is_serving_or_retired_govt_employee": True,
                "is_group_d_class_iv_or_mts": True,
            },
            "family_members": [],
        },
    ),
    ExampleProfile(
        label="Missing-data case",
        scheme_id="PM-KISAN",
        description=(
            "Every field known except citizenship. Demonstrates the undetermined_missing_facts "
            "verdict and the follow-up question loop asking for exactly that one missing fact, "
            "not guessing it."
        ),
        profile={
            "self": dict(_PM_KISAN_BASE_SELF),  # is_indian_citizen deliberately omitted
            "family_members": [],
        },
    ),
    ExampleProfile(
        label="Start from scratch",
        scheme_id="PM-KISAN",
        description=(
            "Empty profile — exercises the full opening-message intake plus the complete "
            "follow-up question loop from zero known facts."
        ),
        profile={"self": {}, "family_members": []},
    ),
]
