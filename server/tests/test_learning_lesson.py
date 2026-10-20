import random
import re
from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from pupil_server.learning.lesson import (
    Attempt,
    BoolResponse,
    ChoiceResponse,
    GradedAttempt,
    Lesson,
    MultipleChoice,
    NumberResponse,
    Numeric,
    Response,
    TeachCard,
    TextMatch,
    TextResponse,
    TrueFalse,
    describe_attempt,
    grade_attempt,
    learner_view,
)
from pupil_server.learning.syllabus import Syllabus

# What every question needs besides its answer.
BASICS = {"prompt": "p", "difficulty": 1, "explanation": "Because."}


def choice(
    qid="q1", correct=("a",), multiple=False, options=("a", "b", "c"), **extra
) -> MultipleChoice:
    return MultipleChoice(
        id=qid,
        **BASICS,
        options=[{"id": o, "text": o.upper()} for o in options],
        correct=list(correct),
        multiple=multiple,
        **extra,
    )


def card(cid="c1") -> TeachCard:
    return TeachCard(id=cid, title="New idea", text="Here it is.")


# Questions


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"correct": ("a", "b")}, "has 2 correct options; set multiple=true or mark exactly one"),
        ({"correct": ("z",)}, "marks unknown options correct: ['z']"),
        ({"options": ("a", "a", "b")}, "duplicate option ids: ['a']"),
        ({"correct": ("a", "a"), "multiple": True}, "lists a correct option twice"),
    ],
    ids=["single-with-two", "unknown-correct", "duplicate-option", "correct-twice"],
)
def test_multiple_choice_validation(kwargs, message):
    with pytest.raises(ValidationError, match=re.escape(message)):
        choice(**kwargs)


def test_questions_need_an_explanation():
    with pytest.raises(ValidationError, match="explanation"):
        TrueFalse(id="q", prompt="p", difficulty=1, answer=True)


def test_multiple_choice_grading():
    single = choice(correct=("b",))
    assert single.grade(ChoiceResponse(option_ids=["b"]))
    assert not single.grade(ChoiceResponse(option_ids=["a"]))
    assert not single.grade(ChoiceResponse(option_ids=["a", "b"]))

    several = choice(correct=("a", "c"), multiple=True)
    assert several.grade(ChoiceResponse(option_ids=["c", "a"]))
    assert not several.grade(ChoiceResponse(option_ids=["a"]))  # a subset is not enough
    assert not several.grade(ChoiceResponse(option_ids=["a", "b", "c"]))


def test_true_false_grading():
    q = TrueFalse(id="q", **BASICS, answer=True)
    assert q.grade(BoolResponse(value=True))
    assert not q.grade(BoolResponse(value=False))


def test_numeric_tolerance_is_inclusive():
    q = Numeric(id="q", **BASICS, answer=10, tolerance=0.5)
    assert q.grade(NumberResponse(value=10.5))
    assert q.grade(NumberResponse(value=9.5))
    assert not q.grade(NumberResponse(value=10.51))
    exact = Numeric(id="q", **BASICS, answer=32)
    assert exact.grade(NumberResponse(value=32)) and not exact.grade(NumberResponse(value=32.01))


def test_numeric_rejects_negative_tolerance_and_nan():
    with pytest.raises(ValidationError):
        Numeric(id="q", **BASICS, answer=1, tolerance=-1)
    with pytest.raises(ValidationError):
        Numeric(id="q", **BASICS, answer=float("nan"))


def test_text_match_normalizes_whitespace_and_case():
    q = TextMatch(id="q", **BASICS, accepted=["def"])
    assert q.grade(TextResponse(text="  DEF "))
    assert not q.grade(TextResponse(text="define"))

    phrase = TextMatch(id="q", **BASICS, accepted=["for  loop"])
    assert phrase.grade(TextResponse(text="For\tLoop"))

    strict = TextMatch(id="q", **BASICS, accepted=["None"], case_sensitive=True)
    assert strict.grade(TextResponse(text=" None"))
    assert not strict.grade(TextResponse(text="none"))


def test_text_match_rejects_blank_accepted_answers():
    with pytest.raises(ValidationError, match="accepts a blank answer"):
        TextMatch(id="q", **BASICS, accepted=["ok", "   "])


def test_wrong_response_kind_is_an_error():
    with pytest.raises(TypeError, match="needs a BoolResponse, got TextResponse"):
        TrueFalse(id="q", **BASICS, answer=True).grade(TextResponse(text="yes"))


@pytest.mark.parametrize(
    ("question", "shown"),
    [
        (choice(correct=("c", "a"), multiple=True), "A, C"),
        (TrueFalse(id="q", **BASICS, answer=False), "False"),
        (Numeric(id="q", **BASICS, answer=3), "3"),
        (Numeric(id="q", **BASICS, answer=2.5, tolerance=0.1, unit="cm"), "2.5 cm (± 0.1)"),
        (TextMatch(id="q", **BASICS, accepted=["def", "DEF"]), "def"),
    ],
    ids=["choice", "true-false", "number", "number-with-unit", "text"],
)
def test_answer_text_is_what_the_learner_sees(question, shown):
    assert question.answer_text() == shown


# Lessons


def lesson(
    syllabus_id: str | None = None, tags: tuple[str, ...] = (), items: list | None = None
) -> Lesson:
    return Lesson(
        id="les_1",
        title="Placement",
        purpose="placement" if syllabus_id is None else "lesson",
        syllabus_id=syllabus_id,
        items=items
        or [
            choice("q1", correct=("a",)).model_copy(update={"objective_ids": list(tags)}),
            TrueFalse(id="q2", **BASICS, answer=False, objective_ids=list(tags)),
        ],
    )


def test_lesson_rejects_duplicate_item_ids():
    with pytest.raises(ValidationError, match=re.escape("duplicate item ids: ['q1']")):
        Lesson(id="les", title="t", purpose="placement", items=[choice("q1"), card("q1")])


def test_lesson_needs_a_question():
    with pytest.raises(ValidationError, match="needs at least one question"):
        Lesson(id="les", title="t", purpose="lesson", syllabus_id="syl_1", items=[card()])


def test_placement_has_no_teach_cards():
    with pytest.raises(ValidationError, match=re.escape("has no teach cards: ['c1']")):
        Lesson(id="les", title="t", purpose="placement", items=[card(), choice("q1")])


def test_a_lesson_needs_a_syllabus():
    with pytest.raises(ValidationError, match="a lesson needs a syllabus_id"):
        Lesson(id="les", title="t", purpose="lesson", items=[choice("q1")])


def test_lesson_without_a_syllabus_rejects_tags():
    with pytest.raises(
        ValidationError, match=re.escape("questions tagged without a syllabus_id: ['q1', 'q2']")
    ):
        lesson(tags=("obj_a",))


def test_grade_attempt_counts_unanswered_as_incorrect_and_skips_cards():
    tagged = lesson("syl_1", tags=("obj_a",))
    with_card = tagged.model_copy(update={"items": [card(), *tagged.items]})
    attempt = Attempt(
        id="att_1",
        lesson_id="les_1",
        responses={"q1": ChoiceResponse(option_ids=["a"])},
        submitted_at=datetime.now(UTC),
    )
    results = grade_attempt(with_card, attempt)
    assert [(r.question_id, r.correct) for r in results] == [("q1", True), ("q2", False)]
    assert results[0].objective_ids == ["obj_a"]


def test_grade_attempt_rejects_unknown_questions_and_other_lessons():
    stray = Attempt(
        id="att",
        lesson_id="les_1",
        responses={"q9": BoolResponse(value=True)},
        submitted_at=datetime.now(UTC),
    )
    with pytest.raises(ValueError, match=re.escape("not in lesson 'les_1': ['q9']")):
        grade_attempt(lesson(), stray)
    other = stray.model_copy(update={"lesson_id": "les_2", "responses": {}})
    with pytest.raises(ValueError, match="attempt is for lesson 'les_2'"):
        grade_attempt(lesson(), other)


SYLLABUS = Syllabus(
    id="syl_1",
    topic="Python",
    goal="g",
    units=[{"id": "u1", "title": "U", "summary": "", "objectives": [{"id": "obj_a", "text": "a"}]}],
)


def test_check_tags():
    lesson("syl_1", tags=("obj_a",)).check_tags(SYLLABUS)
    with pytest.raises(
        ValueError, match=re.escape("questions without objective ids: ['q1', 'q2']")
    ):
        lesson("syl_1").check_tags(SYLLABUS)
    with pytest.raises(ValueError, match=re.escape("not in syllabus 'syl_1': ['obj_zzz']")):
        lesson("syl_1", tags=("obj_zzz",)).check_tags(SYLLABUS)
    with pytest.raises(ValueError, match="lesson is for syllabus 'syl_2'"):
        lesson("syl_2", tags=("obj_a",)).check_tags(SYLLABUS)


@pytest.mark.parametrize(
    "response",
    [
        ChoiceResponse(option_ids=["a"]),
        BoolResponse(value=False),
        NumberResponse(value=1.5),
        TextResponse(text="x"),
    ],
    ids=lambda r: r.kind,
)
def test_responses_round_trip_through_json_by_kind(response):
    # Stored as JSON; `kind` must bring back the same response type, not just equal fields.
    adapter = TypeAdapter(Response)
    restored = adapter.validate_json(adapter.dump_json(response))
    assert type(restored) is type(response) and restored == response


# The learner's view


def mixed_lesson() -> Lesson:
    return Lesson(
        id="les_1",
        title="Mixed",
        purpose="lesson",
        syllabus_id="syl_1",
        items=[
            card("c1"),
            choice("q1", correct=("b",)).model_copy(update={"explanation": "B is right"}),
            TrueFalse(id="q2", **BASICS, answer=True),
            Numeric(id="q3", **BASICS, answer=3, tolerance=0.5, unit="cm"),
            card("c2"),
            TextMatch(id="q4", **BASICS, accepted=["def"]),
            TrueFalse(id="q5", **BASICS, answer=False),
        ],
    )


def test_learner_view_leaves_out_answers_and_explanations():
    view = learner_view(mixed_lesson())
    shown = view.model_dump_json()
    for secret in ("correct", "answer", "accepted", "tolerance", "explanation", "B is right"):
        assert secret not in shown
    c1, q1, q2, q3, *_ = view.items
    assert (c1.kind, c1.title, c1.text) == ("teach_card", "New idea", "Here it is.")
    assert [o.id for o in q1.options] == ["a", "b", "c"]
    assert q1.multiple is False
    assert q3.unit == "cm"
    assert q2.kind == "true_false"


class Reversing(random.Random):
    """Shuffles by reversing, so a test can tell exactly what was shuffled."""

    def shuffle(self, x):
        x.reverse()


def ids(view) -> list[str]:
    return [i.id for i in view.items]


def test_questions_are_shuffled_only_between_teach_cards():
    view = learner_view(mixed_lesson(), Reversing())
    assert ids(view) == ["c1", "q3", "q2", "q1", "c2", "q5", "q4"]
    assert [o.id for o in view.items[3].options] == ["c", "b", "a"]


def test_a_lesson_can_keep_its_order():
    kept = mixed_lesson().model_copy(update={"keep_order": True})
    view = learner_view(kept, Reversing())
    assert ids(view) == ["c1", "q1", "q2", "q3", "c2", "q4", "q5"]


def test_a_question_can_keep_its_option_order():
    kept = lesson(items=[choice("q1", keep_option_order=True)])
    view = learner_view(kept, Reversing())
    assert [o.id for o in view.items[0].options] == ["a", "b", "c"]


def test_describe_attempt_says_what_the_learner_answered():
    lesson = mixed_lesson()
    attempt = Attempt(
        id="att_1",
        lesson_id="les_1",
        responses={
            "q1": ChoiceResponse(option_ids=["a"]),
            "q2": BoolResponse(value=True),
            "q3": NumberResponse(value=5),
            "q5": BoolResponse(value=False),
        },
        submitted_at=datetime.now(UTC),
    )
    graded = GradedAttempt(attempt=attempt, number=2, results=grade_attempt(lesson, attempt))
    assert describe_attempt(lesson, graded).splitlines() == [
        "'Mixed' (les_1), attempt 2: 2 of 5 right.",
        "- q1: wrong, answered 'A'",
        "- q2: right",
        "- q3: wrong, answered 5 cm",
        "- q4: wrong, skipped",
        "- q5: right",
    ]
