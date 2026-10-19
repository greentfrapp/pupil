import re
from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from pupil_server.learning.quiz import (
    BoolResponse,
    ChoiceResponse,
    MultipleChoice,
    NumberResponse,
    Numeric,
    Quiz,
    QuizAttempt,
    Response,
    TextMatch,
    TextResponse,
    TrueFalse,
    grade_attempt,
)
from pupil_server.learning.syllabus import Syllabus


def choice(qid="q1", correct=("a",), multiple=False, options=("a", "b", "c")) -> MultipleChoice:
    return MultipleChoice(
        id=qid,
        prompt="Pick",
        difficulty=2,
        options=[{"id": o, "text": o.upper()} for o in options],
        correct=list(correct),
        multiple=multiple,
    )


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
    q = TrueFalse(id="q", prompt="Python is compiled to bytecode", difficulty=1, answer=True)
    assert q.grade(BoolResponse(value=True))
    assert not q.grade(BoolResponse(value=False))


def test_numeric_tolerance_is_inclusive():
    q = Numeric(id="q", prompt="len('hello world')?", difficulty=1, answer=10, tolerance=0.5)
    assert q.grade(NumberResponse(value=10.5))
    assert q.grade(NumberResponse(value=9.5))
    assert not q.grade(NumberResponse(value=10.51))
    exact = Numeric(id="q", prompt="2 ** 5?", difficulty=1, answer=32)
    assert exact.grade(NumberResponse(value=32)) and not exact.grade(NumberResponse(value=32.01))


def test_numeric_rejects_negative_tolerance_and_nan():
    with pytest.raises(ValidationError):
        Numeric(id="q", prompt="p", difficulty=1, answer=1, tolerance=-1)
    with pytest.raises(ValidationError):
        Numeric(id="q", prompt="p", difficulty=1, answer=float("nan"))


def test_text_match_normalizes_whitespace_and_case():
    q = TextMatch(id="q", prompt="Keyword to define a function?", difficulty=1, accepted=["def"])
    assert q.grade(TextResponse(text="  DEF "))
    assert not q.grade(TextResponse(text="define"))

    phrase = TextMatch(id="q", prompt="p", difficulty=1, accepted=["for  loop"])
    assert phrase.grade(TextResponse(text="For\tLoop"))

    strict = TextMatch(id="q", prompt="p", difficulty=1, accepted=["None"], case_sensitive=True)
    assert strict.grade(TextResponse(text=" None"))
    assert not strict.grade(TextResponse(text="none"))


def test_text_match_rejects_blank_accepted_answers():
    with pytest.raises(ValidationError, match="accepts a blank answer"):
        TextMatch(id="q", prompt="p", difficulty=1, accepted=["ok", "   "])


def test_wrong_response_kind_is_an_error():
    with pytest.raises(TypeError, match="needs a BoolResponse, got TextResponse"):
        TrueFalse(id="q", prompt="p", difficulty=1, answer=True).grade(TextResponse(text="yes"))


def quiz(syllabus_id: str | None = None, tags: tuple[str, ...] = ()) -> Quiz:
    return Quiz(
        id="quiz_1",
        title="Placement",
        purpose="placement" if syllabus_id is None else "checkpoint",
        syllabus_id=syllabus_id,
        questions=[
            choice("q1", correct=("a",)).model_copy(update={"objective_ids": list(tags)}),
            TrueFalse(id="q2", prompt="p", difficulty=1, answer=False, objective_ids=list(tags)),
        ],
    )


def test_quiz_rejects_duplicate_question_ids():
    with pytest.raises(ValidationError, match=re.escape("duplicate question ids: ['q1']")):
        Quiz(id="quiz", title="t", purpose="placement", questions=[choice("q1"), choice("q1")])


def test_checkpoint_quiz_needs_a_syllabus():
    with pytest.raises(ValidationError, match="a checkpoint quiz needs a syllabus_id"):
        Quiz(id="quiz", title="t", purpose="checkpoint", questions=[choice("q1")])


def test_quiz_without_a_syllabus_rejects_tags():
    with pytest.raises(
        ValidationError, match=re.escape("questions tagged without a syllabus_id: ['q1', 'q2']")
    ):
        quiz(tags=("obj_a",))


def test_grade_attempt_counts_unanswered_as_incorrect():
    q = quiz("syl_1", tags=("obj_a",))
    attempt = QuizAttempt(
        id="att_1",
        quiz_id="quiz_1",
        responses={"q1": ChoiceResponse(option_ids=["a"])},
        submitted_at=datetime.now(UTC),
    )
    results = grade_attempt(q, attempt)
    assert [(r.question_id, r.correct) for r in results] == [("q1", True), ("q2", False)]
    assert results[0].objective_ids == ["obj_a"]


def test_grade_attempt_rejects_unknown_questions_and_other_quizzes():
    q = quiz()
    stray = QuizAttempt(
        id="att",
        quiz_id="quiz_1",
        responses={"q9": BoolResponse(value=True)},
        submitted_at=datetime.now(UTC),
    )
    with pytest.raises(ValueError, match=re.escape("not in quiz 'quiz_1': ['q9']")):
        grade_attempt(q, stray)
    other = stray.model_copy(update={"quiz_id": "quiz_2", "responses": {}})
    with pytest.raises(ValueError, match="attempt is for quiz 'quiz_2'"):
        grade_attempt(q, other)


SYLLABUS = Syllabus(
    id="syl_1",
    topic="Python",
    goal="g",
    units=[{"id": "u1", "title": "U", "summary": "", "objectives": [{"id": "obj_a", "text": "a"}]}],
)


def test_check_tags():
    quiz("syl_1", tags=("obj_a",)).check_tags(SYLLABUS)
    with pytest.raises(
        ValueError, match=re.escape("questions without objective ids: ['q1', 'q2']")
    ):
        quiz("syl_1").check_tags(SYLLABUS)
    with pytest.raises(ValueError, match=re.escape("not in syllabus 'syl_1': ['obj_zzz']")):
        quiz("syl_1", tags=("obj_zzz",)).check_tags(SYLLABUS)
    with pytest.raises(ValueError, match="quiz is for syllabus 'syl_2'"):
        quiz("syl_2", tags=("obj_a",)).check_tags(SYLLABUS)


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
    # Stored as JSON later; `kind` must bring back the same response type, not just equal fields.
    adapter = TypeAdapter(Response)
    restored = adapter.validate_json(adapter.dump_json(response))
    assert type(restored) is type(response) and restored == response
