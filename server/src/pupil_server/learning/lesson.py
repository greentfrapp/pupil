"""Lessons: short runs of questions, with the odd teach card, that teach mostly by asking.

A placement lesson finds the learner's level, usually before a syllabus exists; every other
lesson teaches objectives from a syllabus.

Answers are graded by the lesson player, in code, never by a model. The server doesn't grade
again: it checks that a submitted attempt fits the lesson, and stores the results it was sent
along with the learner's responses, so results could be regraded if grading ever had a bug.
"""

from __future__ import annotations

import random
from collections import Counter
from typing import Annotated, ClassVar, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from pupil_server.learning.syllabus import Syllabus

# Responses: what the learner answered. Each question type accepts exactly one kind.


class ChoiceResponse(BaseModel):
    """An answer to a multiple_choice question: the ids of the options picked."""

    kind: Literal["choice"] = "choice"
    option_ids: list[str]


class BoolResponse(BaseModel):
    """An answer to a true_false question."""

    kind: Literal["bool"] = "bool"
    value: bool


class NumberResponse(BaseModel):
    """An answer to a numeric question."""

    kind: Literal["number"] = "number"
    value: float = Field(allow_inf_nan=False)


class TextResponse(BaseModel):
    """An answer to a text_match question."""

    kind: Literal["text"] = "text"
    text: str


Response = Annotated[
    ChoiceResponse | BoolResponse | NumberResponse | TextResponse, Field(discriminator="kind")
]


class QuestionBase(BaseModel):
    # Field docstrings become descriptions in the schema an agent sees.
    model_config = ConfigDict(use_attribute_docstrings=True)

    response_type: ClassVar[type[BaseModel]]
    """The kind of response that answers this type of question."""

    kind: str
    id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    objective_ids: list[str] = Field(default_factory=list)
    """Syllabus objectives this question tests; required once the lesson is tied to a syllabus."""
    difficulty: int = Field(ge=1, le=5)
    """1 (easiest) to 5."""
    explanation: str = Field(min_length=1)
    """One or two sentences on why the answer is right. Shown after the learner answers, right
    or wrong, so a lucky guess still teaches."""

    def check_response(self, response: BaseModel) -> None:
        """Refuse a response that can't be an answer to this question."""
        if not isinstance(response, self.response_type):
            raise TypeError(
                f"question {self.id!r} ({self.kind}) needs a {self.response_type.__name__}, "
                f"got {type(response).__name__}"
            )


class Option(BaseModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class MultipleChoice(QuestionBase):
    """Answered by picking one option, or every correct option when multiple is true."""

    response_type = ChoiceResponse

    kind: Literal["multiple_choice"] = "multiple_choice"
    options: list[Option] = Field(min_length=2)
    correct: list[str] = Field(min_length=1)
    """Ids of the correct options."""
    multiple: bool = False
    """Whether the learner should pick every correct option rather than exactly one."""
    keep_option_order: bool = False
    """Set when the options only make sense in the order given, e.g. 'All of the above' or
    ranges. Otherwise they are shuffled each time the lesson is taken."""

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

    def check_response(self, response: BaseModel) -> None:
        super().check_response(response)
        assert isinstance(response, ChoiceResponse)
        unknown = sorted(set(response.option_ids) - {o.id for o in self.options})
        if unknown:
            raise ValueError(f"question {self.id!r} has no options {unknown}")


class TrueFalse(QuestionBase):
    """A statement the learner says is true or false."""

    response_type = BoolResponse

    kind: Literal["true_false"] = "true_false"
    answer: bool


class Numeric(QuestionBase):
    """Answered with a number."""

    response_type = NumberResponse

    kind: Literal["numeric"] = "numeric"
    answer: float = Field(allow_inf_nan=False)
    tolerance: float = Field(default=0, ge=0, allow_inf_nan=False)
    """How far from the answer still counts as right."""
    unit: str | None = None
    """The unit the answer is in, if any, e.g. 'cm'."""


class TextMatch(QuestionBase):
    """Answered with a short text that must match an accepted answer."""

    response_type = TextResponse

    kind: Literal["text_match"] = "text_match"
    accepted: list[str] = Field(min_length=1)
    """Every answer that counts as right, the best one first: it is the one shown to the
    learner. Spacing, and case unless case_sensitive, are ignored."""
    case_sensitive: bool = False

    @model_validator(mode="after")
    def _check_accepted(self) -> TextMatch:
        if not all(a.strip() for a in self.accepted):
            raise ValueError(f"question {self.id!r} accepts a blank answer")
        return self


AnyQuestion = MultipleChoice | TrueFalse | Numeric | TextMatch
Question = Annotated[AnyQuestion, Field(discriminator="kind")]


class TeachCard(BaseModel):
    """A short piece of teaching, shown before the questions that use it."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    kind: Literal["teach_card"] = "teach_card"
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    """A few sentences introducing a brand-new idea that the questions after it build on."""


Item = Annotated[AnyQuestion | TeachCard, Field(discriminator="kind")]


class Lesson(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    purpose: Literal["placement", "lesson"]
    syllabus_id: str | None = None
    """None for a placement lesson written before any syllabus exists."""
    keep_order: bool = False
    """Set when the questions build on each other. Otherwise they are shuffled each time the
    lesson is taken, though never past a teach card."""
    items: list[Item] = Field(min_length=1)

    @property
    def questions(self) -> list[AnyQuestion]:
        return [i for i in self.items if not isinstance(i, TeachCard)]

    @model_validator(mode="after")
    def _check_structure(self) -> Lesson:
        ids = [i.id for i in self.items]
        duplicates = sorted(i for i, n in Counter(ids).items() if n > 1)
        if duplicates:
            raise ValueError(f"duplicate item ids: {duplicates}")
        if not self.questions:
            raise ValueError("a lesson needs at least one question")
        if self.purpose == "placement":
            cards = [i.id for i in self.items if isinstance(i, TeachCard)]
            if cards:
                raise ValueError(f"a placement lesson measures, so has no teach cards: {cards}")
        if self.syllabus_id is None:
            if self.purpose == "lesson":
                raise ValueError("a lesson needs a syllabus_id; only placement comes before one")
            tagged = [q.id for q in self.questions if q.objective_ids]
            if tagged:
                raise ValueError(f"questions tagged without a syllabus_id: {tagged}")
        return self

    def check_tags(self, syllabus: Syllabus) -> None:
        """Every question must test at least one objective, and only ones the syllabus has."""
        if self.syllabus_id != syllabus.id:
            raise ValueError(f"lesson is for syllabus {self.syllabus_id!r}, not {syllabus.id!r}")
        untagged = [q.id for q in self.questions if not q.objective_ids]
        if untagged:
            raise ValueError(f"questions without objective ids: {untagged}")
        known = syllabus.objective_ids()
        unknown = sorted({t for q in self.questions for t in q.objective_ids} - known)
        if unknown:
            raise ValueError(f"objective ids not in syllabus {syllabus.id!r}: {unknown}")


def shuffled(lesson: Lesson, rng: random.Random) -> Lesson:
    """The lesson in the order the learner takes it this time.

    Questions are shuffled only between teach cards, so a card still comes before the
    questions that use it, and not at all when the lesson keeps its order. Options are
    shuffled unless the question keeps their order.
    """
    items: list[AnyQuestion | TeachCard] = []
    run: list[AnyQuestion | TeachCard] = []  # questions since the last card
    for item in lesson.items:
        if isinstance(item, MultipleChoice) and not item.keep_option_order:
            options = list(item.options)
            rng.shuffle(options)
            item = item.model_copy(update={"options": options})
        if isinstance(item, TeachCard):
            if not lesson.keep_order:
                rng.shuffle(run)
            items += [*run, item]
            run = []
        else:
            run.append(item)
    if not lesson.keep_order:
        rng.shuffle(run)
    return lesson.model_copy(update={"items": items + run})


class Answer(BaseModel):
    """The learner's answer to one question, as the lesson player graded it."""

    response: Response | None
    """None if the learner skipped the question."""
    correct: bool


class Attempt(BaseModel):
    """One run through a lesson, submitted when the learner finishes it."""

    id: str = Field(min_length=1)
    lesson_id: str
    answers: dict[str, Answer]
    """Question id to the learner's answer, for every question in the lesson."""
    submitted_at: AwareDatetime


class QuestionResult(BaseModel):
    question_id: str
    correct: bool
    objective_ids: list[str]


class GradedAttempt(BaseModel):
    attempt: Attempt
    number: int
    """1 for the learner's first attempt at the lesson, 2 for the first retry, and so on."""
    results: list[QuestionResult]
    """One per question, in lesson order."""

    @property
    def correct(self) -> int:
        return sum(r.correct for r in self.results)


def check_attempt(lesson: Lesson, attempt: Attempt) -> list[QuestionResult]:
    """The attempt's results, one per question in lesson order, if it fits the lesson.

    It must answer every question and nothing else, each with the right kind of response.
    Which objectives a question tests comes from the lesson, never from the attempt.
    """
    if attempt.lesson_id != lesson.id:
        raise ValueError(f"attempt is for lesson {attempt.lesson_id!r}, not {lesson.id!r}")
    question_ids = {q.id for q in lesson.questions}
    unknown = sorted(attempt.answers.keys() - question_ids)
    if unknown:
        raise ValueError(f"answers to questions not in lesson {lesson.id!r}: {unknown}")
    missing = sorted(question_ids - attempt.answers.keys())
    if missing:
        raise ValueError(f"no answers to questions {missing}")
    results = []
    for q in lesson.questions:
        answer = attempt.answers[q.id]
        if answer.response is None:
            if answer.correct:
                raise ValueError(f"question {q.id!r} was skipped, so can't be correct")
        else:
            q.check_response(answer.response)
        results.append(
            QuestionResult(question_id=q.id, correct=answer.correct, objective_ids=q.objective_ids)
        )
    return results


def describe_attempt(lesson: Lesson, graded: GradedAttempt) -> str:
    """The results in words, for the agent: what was right, and what the learner answered."""
    questions = {q.id: q for q in lesson.questions}
    score = f"{graded.correct} of {len(graded.results)} right"
    lines = [f"{lesson.title!r} ({lesson.id}), attempt {graded.number}: {score}."]
    for r in graded.results:
        response = graded.attempt.answers[r.question_id].response
        if r.correct:
            lines.append(f"- {r.question_id}: right")
        elif response is None:
            lines.append(f"- {r.question_id}: wrong, skipped")
        else:
            given = _describe_response(questions[r.question_id], response)
            lines.append(f"- {r.question_id}: wrong, answered {given}")
    return "\n".join(lines)


def _describe_response(question: QuestionBase, response: BaseModel) -> str:
    match response:
        case ChoiceResponse(option_ids=ids) if isinstance(question, MultipleChoice):
            texts = {o.id: o.text for o in question.options}
            return ", ".join(repr(texts.get(i, i)) for i in ids) or "nothing"
        case BoolResponse(value=value):
            return "true" if value else "false"
        case NumberResponse(value=value):
            unit = getattr(question, "unit", None)
            return f"{value:g} {unit}" if unit else f"{value:g}"
        case TextResponse(text=text):
            return repr(text)
    return repr(response)
