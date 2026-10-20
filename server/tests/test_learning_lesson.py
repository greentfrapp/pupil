import random
import re
from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from pupil_server.learning.lesson import (
    Answer,
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
    check_attempt,
    describe_attempt,
    shuffled,
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


def test_numeric_rejects_negative_tolerance_and_nan():
    with pytest.raises(ValidationError):
        Numeric(id="q", **BASICS, answer=1, tolerance=-1)
    with pytest.raises(ValidationError):
        Numeric(id="q", **BASICS, answer=float("nan"))


def test_text_match_rejects_blank_accepted_answers():
    with pytest.raises(ValidationError, match="accepts a blank answer"):
        TextMatch(id="q", **BASICS, accepted=["ok", "   "])


def test_a_response_of_the_wrong_kind_is_refused():
    with pytest.raises(TypeError, match="needs a BoolResponse, got TextResponse"):
        TrueFalse(id="q", **BASICS, answer=True).check_response(TextResponse(text="yes"))


def test_a_choice_of_unknown_options_is_refused():
    with pytest.raises(ValueError, match=re.escape("has no options ['z']")):
        choice().check_response(ChoiceResponse(option_ids=["a", "z"]))


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


# Shuffling


def mixed_lesson() -> Lesson:
    return Lesson(
        id="les_1",
        title="Mixed",
        purpose="lesson",
        syllabus_id="syl_1",
        items=[
            card("c1"),
            choice("q1", correct=("b",)),
            TrueFalse(id="q2", **BASICS, answer=True),
            Numeric(id="q3", **BASICS, answer=3, tolerance=0.5, unit="cm"),
            card("c2"),
            TextMatch(id="q4", **BASICS, accepted=["def"]),
            TrueFalse(id="q5", **BASICS, answer=False),
        ],
    )


class Reversing(random.Random):
    """Shuffles by reversing, so a test can tell exactly what was shuffled."""

    def shuffle(self, x):
        x.reverse()


def ids(lesson: Lesson) -> list[str]:
    return [i.id for i in lesson.items]


def test_questions_are_shuffled_only_between_teach_cards():
    played = shuffled(mixed_lesson(), Reversing())
    assert ids(played) == ["c1", "q3", "q2", "q1", "c2", "q5", "q4"]
    assert [o.id for o in played.items[3].options] == ["c", "b", "a"]


def test_a_lesson_can_keep_its_order():
    kept = mixed_lesson().model_copy(update={"keep_order": True})
    assert ids(shuffled(kept, Reversing())) == ["c1", "q1", "q2", "q3", "c2", "q4", "q5"]


def test_a_question_can_keep_its_option_order():
    kept = lesson(items=[choice("q1", keep_option_order=True)])
    played = shuffled(kept, Reversing())
    assert [o.id for o in played.items[0].options] == ["a", "b", "c"]


# Attempts


def attempt(**answers: Answer) -> Attempt:
    return Attempt(id="att_1", lesson_id="les_1", answers=answers, submitted_at=datetime.now(UTC))


def right(response) -> Answer:
    return Answer(response=response, correct=True)


def wrong(response) -> Answer:
    return Answer(response=response, correct=False)


SKIPPED = Answer(response=None, correct=False)


def test_check_attempt_takes_the_grades_and_the_lessons_tags():
    tagged = lesson("syl_1", tags=("obj_a",))
    with_card = tagged.model_copy(update={"items": [card(), *tagged.items]})
    sent = attempt(q2=SKIPPED, q1=right(ChoiceResponse(option_ids=["a"])))
    results = check_attempt(with_card, sent)
    assert [(r.question_id, r.correct) for r in results] == [("q1", True), ("q2", False)]
    assert results[0].objective_ids == ["obj_a"]


@pytest.mark.parametrize(
    ("answers", "message"),
    [
        ({"q1": SKIPPED}, "no answers to questions ['q2']"),
        ({"q1": SKIPPED, "q2": SKIPPED, "q9": SKIPPED}, "not in lesson 'les_1': ['q9']"),
        ({"q1": SKIPPED, "q2": wrong(TextResponse(text="no"))}, "needs a BoolResponse"),
        ({"q1": SKIPPED, "q2": Answer(response=None, correct=True)}, "skipped, so can't be"),
    ],
    ids=["missing", "unknown", "wrong-kind", "skipped-but-right"],
)
def test_check_attempt_refuses_attempts_that_dont_fit(answers, message):
    with pytest.raises((ValueError, TypeError), match=re.escape(message)):
        check_attempt(lesson(), attempt(**answers))


def test_check_attempt_refuses_another_lessons_attempt():
    other = attempt(q1=SKIPPED, q2=SKIPPED).model_copy(update={"lesson_id": "les_2"})
    with pytest.raises(ValueError, match="attempt is for lesson 'les_2'"):
        check_attempt(lesson(), other)


def test_describe_attempt_says_what_the_learner_answered():
    lesson = mixed_lesson()
    sent = attempt(
        q1=wrong(ChoiceResponse(option_ids=["a"])),
        q2=right(BoolResponse(value=True)),
        q3=wrong(NumberResponse(value=5)),
        q4=SKIPPED,
        q5=right(BoolResponse(value=False)),
    )
    graded = GradedAttempt(attempt=sent, number=2, results=check_attempt(lesson, sent))
    assert describe_attempt(lesson, graded).splitlines() == [
        "'Mixed' (les_1), attempt 2: 2 of 5 right.",
        "- q1: wrong, answered 'A'",
        "- q2: right",
        "- q3: wrong, answered 5 cm",
        "- q4: wrong, skipped",
        "- q5: right",
    ]
