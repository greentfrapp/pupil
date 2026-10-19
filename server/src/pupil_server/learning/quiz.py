"""Quizzes: placement before a syllabus exists, checkpoints against one.

Every question type is graded by code, never by a model, so results are reproducible.
"""

from __future__ import annotations

from collections import Counter
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from pupil_server.learning.syllabus import Syllabus

# Responses: what the learner answered. Each question type accepts exactly one kind.


class ChoiceResponse(BaseModel):
    kind: Literal["choice"] = "choice"
    option_ids: list[str]


class BoolResponse(BaseModel):
    kind: Literal["bool"] = "bool"
    value: bool


class NumberResponse(BaseModel):
    kind: Literal["number"] = "number"
    value: float = Field(allow_inf_nan=False)


class TextResponse(BaseModel):
    kind: Literal["text"] = "text"
    text: str


Response = Annotated[
    ChoiceResponse | BoolResponse | NumberResponse | TextResponse, Field(discriminator="kind")
]


def _expect[R: BaseModel](question: QuestionBase, response: BaseModel, kind: type[R]) -> R:
    if not isinstance(response, kind):
        raise TypeError(
            f"question {question.id!r} ({question.kind}) needs a {kind.__name__}, "
            f"got {type(response).__name__}"
        )
    return response


class QuestionBase(BaseModel):
    kind: str
    id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    objective_ids: list[str] = Field(default_factory=list)
    """Syllabus objectives this question tests; required once the quiz is tied to a syllabus."""
    difficulty: int = Field(ge=1, le=5)
    explanation: str | None = None
    """Shown to the learner after they answer."""


class Option(BaseModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class MultipleChoice(QuestionBase):
    kind: Literal["multiple_choice"] = "multiple_choice"
    options: list[Option] = Field(min_length=2)
    correct: list[str] = Field(min_length=1)
    multiple: bool = False
    """Whether the learner should pick every correct option rather than exactly one."""

    @model_validator(mode="after")
    def _check_options(self) -> MultipleChoice:
        option_ids = [o.id for o in self.options]
        duplicates = sorted(i for i, n in Counter(option_ids).items() if n > 1)
        if duplicates:
            raise ValueError(f"question {self.id!r} has duplicate option ids: {duplicates}")
        unknown = [c for c in self.correct if c not in option_ids]
        if unknown:
            raise ValueError(f"question {self.id!r} marks unknown options correct: {unknown}")
        if len(set(self.correct)) != len(self.correct):
            raise ValueError(f"question {self.id!r} lists a correct option twice")
        if not self.multiple and len(self.correct) != 1:
            raise ValueError(
                f"question {self.id!r} has {len(self.correct)} correct options; "
                "set multiple=true or mark exactly one"
            )
        return self

    def grade(self, response: BaseModel) -> bool:
        chosen = _expect(self, response, ChoiceResponse).option_ids
        return set(chosen) == set(self.correct)


class TrueFalse(QuestionBase):
    kind: Literal["true_false"] = "true_false"
    answer: bool

    def grade(self, response: BaseModel) -> bool:
        return _expect(self, response, BoolResponse).value == self.answer


class Numeric(QuestionBase):
    kind: Literal["numeric"] = "numeric"
    answer: float = Field(allow_inf_nan=False)
    tolerance: float = Field(default=0, ge=0, allow_inf_nan=False)
    unit: str | None = None

    def grade(self, response: BaseModel) -> bool:
        return abs(_expect(self, response, NumberResponse).value - self.answer) <= self.tolerance


class TextMatch(QuestionBase):
    kind: Literal["text_match"] = "text_match"
    accepted: list[str] = Field(min_length=1)
    case_sensitive: bool = False

    @model_validator(mode="after")
    def _check_accepted(self) -> TextMatch:
        if not all(self._normalize(a) for a in self.accepted):
            raise ValueError(f"question {self.id!r} accepts a blank answer")
        return self

    def _normalize(self, text: str) -> str:
        collapsed = " ".join(text.split())
        return collapsed if self.case_sensitive else collapsed.casefold()

    def grade(self, response: BaseModel) -> bool:
        given = self._normalize(_expect(self, response, TextResponse).text)
        return given in {self._normalize(a) for a in self.accepted}


Question = Annotated[MultipleChoice | TrueFalse | Numeric | TextMatch, Field(discriminator="kind")]


class Quiz(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    purpose: Literal["placement", "checkpoint"]
    syllabus_id: str | None = None
    """None for a placement quiz written before any syllabus exists."""
    questions: list[Question] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_structure(self) -> Quiz:
        ids = [q.id for q in self.questions]
        duplicates = sorted(i for i, n in Counter(ids).items() if n > 1)
        if duplicates:
            raise ValueError(f"duplicate question ids: {duplicates}")
        if self.syllabus_id is None:
            if self.purpose == "checkpoint":
                raise ValueError("a checkpoint quiz needs a syllabus_id")
            tagged = [q.id for q in self.questions if q.objective_ids]
            if tagged:
                raise ValueError(f"questions tagged without a syllabus_id: {tagged}")
        return self

    def check_tags(self, syllabus: Syllabus) -> None:
        """Every question must test at least one objective, and only ones the syllabus has."""
        if self.syllabus_id != syllabus.id:
            raise ValueError(f"quiz is for syllabus {self.syllabus_id!r}, not {syllabus.id!r}")
        untagged = [q.id for q in self.questions if not q.objective_ids]
        if untagged:
            raise ValueError(f"questions without objective ids: {untagged}")
        known = syllabus.objective_ids()
        unknown = sorted({t for q in self.questions for t in q.objective_ids} - known)
        if unknown:
            raise ValueError(f"objective ids not in syllabus {syllabus.id!r}: {unknown}")


class QuizAttempt(BaseModel):
    id: str = Field(min_length=1)
    quiz_id: str
    responses: dict[str, Response]
    """Question id to the learner's response; unanswered questions are simply absent."""
    submitted_at: AwareDatetime


class QuestionResult(BaseModel):
    question_id: str
    correct: bool
    objective_ids: list[str]


def grade_attempt(quiz: Quiz, attempt: QuizAttempt) -> list[QuestionResult]:
    """One result per question, in quiz order. Unanswered questions count as incorrect."""
    if attempt.quiz_id != quiz.id:
        raise ValueError(f"attempt is for quiz {attempt.quiz_id!r}, not {quiz.id!r}")
    unknown = sorted(attempt.responses.keys() - {q.id for q in quiz.questions})
    if unknown:
        raise ValueError(f"responses to questions not in quiz {quiz.id!r}: {unknown}")
    return [
        QuestionResult(
            question_id=q.id,
            correct=q.id in attempt.responses and q.grade(attempt.responses[q.id]),
            objective_ids=q.objective_ids,
        )
        for q in quiz.questions
    ]
