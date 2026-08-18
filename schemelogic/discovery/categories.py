"""Deterministic keyword-based category tagging for the browse page's filter pills (Farmers,
Students, Women, Health, Housing). No category field exists anywhere in the gold or silver scheme
data -- checked before building this: gold's Scheme model has no domain-category field, and every
key present on a real silver record was enumerated directly against the actual data
(data/silver/schemes.jsonl) and has nothing resembling a category either. This is a cheap, explicit
heuristic over scheme_name + description, not an authoritative myScheme categorization -- it's
wired to REAL filtering (a scheme can match zero, one, or several categories), not decoration that
silently does nothing. "All Schemes" always shows everything regardless of these tags.
"""

from __future__ import annotations

CATEGORIES: tuple[str, ...] = ("farmers", "students", "women", "health", "housing")

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "farmers": (
        "farmer", "farming", "agricult", "krishi", "kisan", "crop", "irrigation", "horticult",
        "animal husbandry", "dairy", "fisher", "livestock", "kcc",
    ),
    "students": (
        "student", "scholarship", "education", "school", "college", "shiksha", "vidya", "study",
        "tuition", "hostel", "university", "academic",
    ),
    "women": (
        "women", "woman", "girl", "mahila", "beti", "widow", "mother", "maternity", "pregnan",
        "self help group", "shg", "kanya",
    ),
    "health": (
        "health", "hospital", "medical", "arogya", "swasthya", "insurance", "treatment",
        "disease", "disability", "divyang", "ayushman", "chikitsa",
    ),
    "housing": ("housing", "awas", " house", "home", "ghar", "shelter", "residen"),
}


def categories_for(scheme_name: str, description: str | None = None) -> set[str]:
    """Which of CATEGORIES this scheme's name/description matches, by plain substring keyword
    presence -- deliberately not fuzzy/weighted, just "does any keyword for this category appear
    anywhere". A scheme can match multiple categories or none; callers should treat "no match" as
    a legitimate, honest outcome, not something to force into a bucket."""
    haystack = f"{scheme_name} {description or ''}".lower()
    return {cat for cat, keywords in _KEYWORDS.items() if any(kw in haystack for kw in keywords)}
