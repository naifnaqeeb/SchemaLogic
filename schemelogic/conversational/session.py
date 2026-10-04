"""In-progress citizen conversation state (Phase 8, Step 2). Pure data + mutation logic — no LLM
call anywhere in this module. Wraps question_selector.py's pure logic into a stateful session an
external caller (the Streamlit UI) can drive turn by turn.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from schemelogic.conversational.question_selector import DECLINE_REPLY, Question, select_next_question
from schemelogic.evaluator.symbolic_engine import EvaluationResult, Verdict, evaluate
from schemelogic.schema.field_ontology import fields_screened_by
from schemelogic.schema.models import Scheme


class AnswerParseError(ValueError):
    """Raised when the raw answer text can't be parsed for the pending question's answer_type.
    The caller (UI) should catch this and re-prompt — never silently guess a value, same
    no-silent-guessing principle the symbolic evaluator itself is built on."""


_DECLINE_PHRASES = (
    "prefer not to say", "prefer not to answer", "rather not say", "rather not answer", "rather not",
    "don't want to say", "dont want to say", "do not want to say", "don't want to answer",
    "do not want to answer", "not comfortable", "no comment", "skip", "pass", "private",
)


def is_decline(raw: str) -> bool:
    """Deterministic: the Prefer-not-to-say button, or a plain decline typed in its own words. Never an
    LLM -- a model reading "I'd rather not" as "no" would turn a decline into a definite verdict."""
    text = " ".join(raw.lower().replace("’", "'").split()).strip(" .!")
    return text == DECLINE_REPLY.lower() or any(
        re.search(rf"(?<![\w']){re.escape(phrase)}(?![\w'])", text) for phrase in _DECLINE_PHRASES)


def _parse_answer(raw: str, answer_type: str) -> Any:
    raw = raw.strip()
    if answer_type == "boolean":
        lowered = raw.lower()
        if lowered in ("yes", "y", "true", "1"):
            return True
        if lowered in ("no", "n", "false", "0"):
            return False
        raise AnswerParseError(f"expected yes/no, got {raw!r}")
    if answer_type == "number":
        try:
            return float(raw) if "." in raw else int(raw)
        except ValueError as exc:
            raise AnswerParseError(f"expected a number, got {raw!r}") from exc
    return raw


@dataclass
class ConversationSession:
    scheme: Scheme
    profile: dict[str, Any] = field(default_factory=lambda: {"self": {}, "family_members": []})
    pending_question: Question | None = None
    declined: tuple[str, str] | None = None  # (member, field) the citizen chose not to disclose
    turns: list[dict[str, str]] = field(default_factory=list)  # {"role": "user"|"assistant", "text": ...}

    def _member_dict(self, member: str) -> dict[str, Any]:
        if member == "self":
            return self.profile.setdefault("self", {})
        idx = int(member[len("family_member[") : -1])
        family = self.profile.setdefault("family_members", [])
        while len(family) <= idx:
            family.append({})
        return family[idx]

    def apply_answer(self, raw_answer: str) -> None:
        """Parses raw_answer per pending_question.answer_type and writes it into the profile.
        Raises AnswerParseError on unparseable input — pending_question is left untouched in
        that case, so the caller can just re-prompt with the same question."""
        if self.pending_question is None:
            raise RuntimeError("apply_answer called with no pending question")
        q = self.pending_question
        value = _parse_answer(raw_answer, q.answer_type)  # raises before any mutation on bad input
        record = self._member_dict(q.member)
        record[q.field] = value
        if value is False:
            for settled in fields_screened_by(q.field):  # not a widow -> not a widow living with HIV/AIDS
                record.setdefault(settled, False)
        self.turns.append({"role": "user", "text": raw_answer})
        self.pending_question = None

    def decline_pending(self) -> None:
        """The citizen chose not to answer a sensitive question. Nothing is written to the profile: the
        fact stays unknown, so the evaluator can't reach a definite verdict from it -- the caller ends
        the check with a pointer to the local office instead of a verdict."""
        q = self.pending_question
        if q is None or not q.allows_decline:
            raise RuntimeError("decline_pending called without a pending sensitive question")
        self.declined = (q.member, q.field)
        self.turns.append({"role": "user", "text": DECLINE_REPLY})
        self.pending_question = None

    def advance(self) -> Question | None:
        """Computes the next question (or None once enough is known for a definite verdict) and
        stores it as pending_question. Never calls an LLM."""
        self.pending_question = select_next_question(self.scheme, self.profile)
        if self.pending_question is not None:
            self.turns.append({"role": "assistant", "text": self.pending_question.prompt})
        return self.pending_question

    def current_result(self) -> EvaluationResult:
        return evaluate(self.scheme, self.profile)

    def is_resolved(self) -> bool:
        return self.current_result().verdict != Verdict.UNDETERMINED
