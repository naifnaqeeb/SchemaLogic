"""Plain-language citizen questions for fields the canonical ontology has never seen.

Why this exists: an AI-Checked extraction proposes field names freely, and most of what it
proposes is novel — 48 of 64 substantive predicates (75%) across the 2026-09-15 live sample. A
novel field has no `citizen_question` in schema/field_ontology.py, so question_selector falls back
to a generic template and the citizen is asked:

    Do you meet this criterion: "is forward community"?
    Do you meet this criterion: "bride education up to 5th"?

against a gold scheme's "What is your monthly pension amount, in rupees?". The conversation is
correct either way — the verdict comes from the same evaluator over the same rules — but this was
the dominant experiential gap between an AI-Checked chat and a Verified one, since it affects
three of every four questions asked.

WHAT THIS MODULE'S LLM CALL MAY PRODUCE: question wording. Nothing else. It never sees a citizen's
answers, never proposes a field, never supplies a value, an operator, a threshold or a category,
and its output never reaches the evaluator — it is substituted for a display string and nothing
more. A failed or rejected call costs nothing but the old generic phrasing (see
`_is_plausible_question` for what gets rejected, and note every caller treats None as "keep the
fallback"). This is the same shape as phrasing.phrase_verdict(), which only words an
already-computed verdict.

Caching is two-level and keyed by FIELD NAME, not by scheme: a field like
`is_registered_ngo` recurs across schemes, so one call serves all of them, for the life of the
disk cache. Failures are never cached — a provider outage must not permanently pin a field to the
generic phrasing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from schemelogic.conversational.question_selector import family_wide_fields
from schemelogic.llm.provider import ProviderFailure, chat_completion_with_fallback
from schemelogic.schema import field_ontology
from schemelogic.schema.models import Scheme

DISK_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "cache" / "field_questions.json"

_MAX_QUESTION_CHARS = 160
_MIN_QUESTION_CHARS = 8

# A generated question that smuggles in a specific number, currency amount or date is asserting a
# threshold the extraction didn't put there -- exactly the fabrication this project exists to
# avoid. The predicate's own value is the evaluator's business; the question must only ask the
# citizen for their fact.
#
# Numbers already present in the FIELD NAME are the exception, and have to be: a field called
# `bride_education_10th_passed` cannot be asked about without saying "10th", and rejecting that
# left it stuck on the generic fallback (measured 2026-09-18). Only digits the model introduced
# on its own are treated as fabrication -- see _introduces_unsourced_specifics.
_CURRENCY_OR_PERCENT = re.compile(r"₹|\brs\.?\b|percent|%", re.IGNORECASE)
_DIGIT_RUN = re.compile(r"\d+")


def _introduces_unsourced_specifics(text: str, field: str) -> bool:
    if _CURRENCY_OR_PERCENT.search(text):
        return True
    sourced = set(_DIGIT_RUN.findall(field))
    return any(n not in sourced for n in _DIGIT_RUN.findall(text))


def _load_disk_cache() -> dict[str, str]:
    try:
        data = json.loads(DISK_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def _save_disk_cache(cache: dict[str, str]) -> None:
    try:
        DISK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        DISK_CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # a cache that can't be written is a cost problem, never a correctness one


_HOUSEHOLD_SUFFIX = "@household"  # disk-cache key suffix for a field's household phrasing


def _system_prompt(answer_type: str, language: str = "en", household: bool = False) -> str:
    shape = {
        "boolean": 'a YES/NO question, answerable with "yes" or "no"',
        "number": "a question asking for a single number",
    }.get(answer_type, "a short question asking for one piece of information")
    prompt = (
        "You write ONE short, plain-language question that an INDIAN GOVERNMENT WELFARE SCHEME "
        "would ask a citizen to find out one specific fact about them. You are NOT deciding "
        "eligibility and NOT stating any rule -- a separate deterministic engine does that. You "
        "only phrase the question.\n\n"
        f"You are given an internal field name. Write {shape}, addressed to the citizen as "
        '"you", in simple language a non-specialist can answer without looking anything up.\n\n'
        "Rules:\n"
        + (
            "- This fact is checked for EVERY member of the citizen's family, so ask whether the "
            "citizen OR ANY MEMBER OF THEIR FAMILY has it (for a number, ask for the highest value "
            "among them), and say \"family\" in the question. "
            if household else "- Ask only for the citizen's own fact. "
        )
        + "Never state or imply a threshold, cut-off, "
        "amount, date or eligibility consequence — you do not know them, and inventing one would "
        "be wrong.\n"
        "- Indian welfare administration terms in the field name are OFFICIAL CATEGORY NAMES, not "
        "descriptive adjectives. Keep them verbatim: 'Forward Community', 'Backward Class', "
        "'Most Backward Class', 'Scheduled Caste', 'Scheduled Tribe', 'BPL', 'APL', 'Group D', "
        "'MTS', 'Aadhaar', 'kutcha', 'pucca'. For example a field named `is_forward_community` "
        "asks whether the person belongs to the Forward Community category — it has nothing to do "
        "with being forward-thinking or progressive.\n"
        "- PRESERVE THE SUBJECT the field name names. If it says bride, ask about the bride; if "
        "it says spouse, household, applicant or family member, ask about exactly that. Never "
        "silently move a question about someone else onto the citizen themselves.\n"
        "- Do not introduce any number, amount, percentage or date that is not already present in "
        "the field name itself.\n"
        "- One sentence, under 20 words, ending in a question mark.\n"
        "- Do not mention the field name, JSON, or that this is an automated system.\n"
        "- Output ONLY the question text, nothing else."
    )
    if language == "hi":
        prompt += "\n- Write the question in Hindi (Devanagari script)."
    return prompt


def _is_plausible_question(text: str, field: str = "", language: str = "en") -> bool:
    """Deliberately strict: a rejected generation costs only the existing generic phrasing, while
    an accepted bad one is shown to a citizen as if the system understood the rule."""
    text = text.strip()
    if not (_MIN_QUESTION_CHARS <= len(text) <= _MAX_QUESTION_CHARS):
        return False
    if not text.endswith("?"):
        return False
    if "\n" in text:
        return False
    if _introduces_unsourced_specifics(text, field):
        return False
    if language == "en" and not _is_about_the_right_person(text, field):
        return False
    return True


def _is_about_the_right_person(text: str, field: str) -> bool:
    """A valid question either addresses the citizen directly ("Do you...") or names the subject
    the field names ("Did the bride..."). Requiring "you" alone was wrong: it rejected exactly the
    third-party phrasings the prompt asks for, so `bride_education_up_to_5th` stayed stuck on the
    generic fallback while the model was producing a perfectly good question about the bride
    (measured 2026-09-18). Also serves as an anti-echo check -- a generation that shares no
    content word with the field and never says "you" isn't about this field at all."""
    if re.search(r"\byou\b|\byour\b", text, re.IGNORECASE):
        return True
    field_tokens = {t for t in field.lower().split("_") if len(t) > 3 and t not in _FIELD_NOISE}
    lowered = text.lower()
    return any(t in lowered for t in field_tokens)


_FIELD_NOISE = frozenset({"has", "is_", "the", "and", "with", "from", "per", "any", "all"})


def phrase_field_question(
    field: str,
    answer_type: str = "boolean",
    language: str = "en",
    cache: dict[str, str] | None = None,
    scheme_context: str | None = None,
    household: bool = False,
) -> str | None:
    """A citizen-facing question for one novel `field`, or None if the caller should keep its own
    fallback phrasing. Never raises. One LLM call per uncached field.

    `scheme_context` is the scheme's name, which disambiguates field names that are meaningless in
    isolation: `is_forward_community` inside "Inter-caste Marriage Assistance Scheme" is plainly
    the caste category, where without that context it was rendered "forward-thinking community"
    (measured 2026-09-18) -- a confident, wrong question, worse for a citizen than the generic
    fallback it replaced.

    The cache is keyed by field name alone, so the first scheme to phrase a shared field decides
    its wording for every later scheme. That's intended -- a field is supposed to be one reusable
    concept -- but it does mean context only influences the FIRST phrasing of a given field."""
    if field_ontology.get_field(field) is not None:
        return None  # canonical fields already have a human-written question

    cache = _load_disk_cache() if cache is None else cache
    key = field + _HOUSEHOLD_SUFFIX if household else field
    if key in cache:
        return cache[key]

    label = field.replace("_", " ").strip()
    user_lines = [f"Field name: {field}", f"Meaning (humanized): {label}"]
    if scheme_context:
        user_lines.append(f"This field appears in the eligibility rules for: {scheme_context}")
    try:
        response = chat_completion_with_fallback(
            [
                {"role": "system", "content": _system_prompt(answer_type, language, household)},
                {"role": "user", "content": "\n".join(user_lines)},
            ],
            temperature=0.0,
            # gpt-oss bills its reasoning tokens against max_tokens, so a cap sized for the
            # ANSWER starves the response: measured 2026-09-18, max_tokens=60 returned empty
            # content with finish_reason='length' for every field (the fallback held, so the only
            # symptom was that the feature silently never worked). 300 leaves room for the
            # reasoning preamble; reasoning_effort="low" keeps that preamble short. Low effort is
            # appropriate here in a way it is NOT for rule extraction -- this call only picks
            # wording, and the 2026-09-15 comparison that showed low effort dropping real
            # predicates was about extracting rules, not phrasing a question.
            max_tokens=300,
            reasoning_effort="low",
        )
    except Exception:  # noqa: BLE001 -- this runs mid-chat; any failure means "keep the fallback"
        return None

    if isinstance(response, ProviderFailure):
        return None

    candidate = (response.content or "").strip().strip('"').strip()
    if not _is_plausible_question(candidate, field, language):
        return None
    if household and language == "en" and not field_ontology.is_household_phrased(candidate):
        return None  # asked about the citizen alone: a relative's fact would never be asked

    cache[key] = candidate
    _save_disk_cache(cache)
    return candidate


def _novel_fields(scheme: Scheme) -> list[tuple[str, str]]:
    """(field, answer_type) for every predicate field in `scheme` the ontology can't phrase.
    answer_type is inferred the same way question_selector does it, so the generated question
    matches the answer affordance the citizen will actually be given (buttons vs free text)."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def answer_type_for(value: object) -> str:
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, (int, float)):
            return "number"
        return "text"

    def walk(node: object) -> None:
        kids = getattr(node, "and_", None) or getattr(node, "or_", None)
        if kids:
            for k in kids:
                walk(k)
            return
        name = getattr(node, "field", None)
        if name and name not in seen:
            seen.add(name)
            if field_ontology.citizen_question_for(name) is None:
                out.append((name, answer_type_for(getattr(node, "value", None))))

    walk(scheme.inclusion)
    for exclusion in scheme.exclusions:
        walk(exclusion)
        if exclusion.except_ is not None:
            walk(exclusion.except_)
    return out


def ensure_questions_for_scheme(scheme: Scheme, language: str = "en") -> int:
    """Generate and register citizen questions for every novel field in `scheme`. Returns how many
    were registered. Best-effort by construction: any field that fails keeps the generic fallback,
    and the Q&A is never blocked or delayed past the calls it actually needs.

    Called once when an AI-Checked extraction is accepted, so the cost lands with the extraction
    rather than mid-conversation, and is paid once per field for the life of the disk cache."""
    cache = _load_disk_cache()
    registered = 0
    context = scheme.scheme_id.replace("-", " ").strip() or None
    family_wide = family_wide_fields(scheme)
    for field, answer_type in _novel_fields(scheme):
        question = phrase_field_question(
            field, answer_type=answer_type, language=language, cache=cache, scheme_context=context
        )
        if question and field_ontology.register_citizen_question(field, question):
            registered += 1
        if field in family_wide:
            # Checked for the whole family: the applicant must be asked about the household. Without
            # a phrasing, question_selector falls back to a generic household question -- never an
            # applicant-only one.
            household = phrase_field_question(
                field, answer_type=answer_type, language=language, cache=cache,
                scheme_context=context, household=True,
            )
            if household and field_ontology.register_household_question(field, household):
                registered += 1
    return registered


def preload_registered_questions() -> int:
    """Register everything already on disk, with no LLM calls at all — so a server restart doesn't
    re-pay for phrasings it has already generated (the disk cache survives the process; the
    in-memory registry does not)."""
    registered = 0
    for key, question in _load_disk_cache().items():
        if key.endswith(_HOUSEHOLD_SUFFIX):
            ok = field_ontology.register_household_question(key[: -len(_HOUSEHOLD_SUFFIX)], question)
        else:
            ok = field_ontology.register_citizen_question(key, question)
        registered += ok
    return registered
