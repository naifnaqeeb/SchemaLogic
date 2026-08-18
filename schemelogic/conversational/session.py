"""In-progress citizen conversation state (Phase 8, Step 2). Pure data + mutation logic — no LLM
call anywhere in this module. Wraps question_selector.py's pure logic into a stateful session an
external caller (the Streamlit UI) can drive turn by turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from schemelogic.conversational.question_selector import Question, select_next_question
from schemelogic.evaluator.symbolic_engine import EvaluationResult, Verdict, evaluate
from schemelogic.schema.models import Scheme


class AnswerParseError(ValueError):
    """Raised when the raw answer text can't be parsed for the pending question's answer_type.
    The caller (UI) should catch this and re-prompt — never silently guess a value, same
    no-silent-guessing principle the symbolic evaluator itself is built on."""


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
        self._member_dict(q.member)[q.field] = value
        self.turns.append({"role": "user", "text": raw_answer})
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
