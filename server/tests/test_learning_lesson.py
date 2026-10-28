import random
import re
from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from pupil_server.learning.lesson import (
    Answer,
    Attempt,
    BlanksResponse,
    BoolResponse,
    ChoiceResponse,
    FillBlank,
    GradedAttempt,
    Lesson,
    Matching,
    MatchResponse,
    MultipleChoice,
    NumberResponse,
    Numeric,
    Ordering,
    OrderResponse,
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


def fill_blank(text="x = ___ + ___", answers=("1", "2"), word_bank=None) -> FillBlank:
    return FillBlank(
        id="q",
        **BASICS,
        text=text,
        blanks=[{"accepted": [a]} for a in answers],
        word_bank=word_bank,
    )


def test_fill_blank_needs_a_blank_for_each_marker():
    with pytest.raises(ValidationError, match="has 2 ___ in its text but 1 blanks"):
        fill_blank(answers=("1",))


def test_a_long_run_of_underscores_is_one_blank():
    assert len(fill_blank("x = ______", answers=("1",)).blanks) == 1


def test_a_word_bank_must_hold_every_answer():
    fill_blank(word_bank=["1", "2", "3"])
    with pytest.raises(ValidationError, match=re.escape("word bank is missing answers: ['2']")):
        fill_blank(word_bank=["1", "3"])
    with pytest.raises(ValidationError, match=re.escape("word bank is missing answers: ['1']")):
        fill_blank(answers=("1", "1"), word_bank=["1", "2"])  # each word fills one blank


def test_fill_blank_responses_must_fit_the_blanks():
    with pytest.raises(ValueError, match="has 2 blanks, got 1 answers"):
        fill_blank().check_response(BlanksResponse(values=["1"]))
    banked = fill_blank(word_bank=["1", "2", "3"])
    banked.check_response(BlanksResponse(values=["3", "2"]))
    with pytest.raises(ValueError, match=re.escape("word bank has no ['9']")):
        banked.check_response(BlanksResponse(values=["1", "9"]))
    with pytest.raises(ValueError, match=re.escape("word bank has no ['1']")):
        banked.check_response(BlanksResponse(values=["1", "1"]))


def ordering(*texts: str) -> Ordering:
    return Ordering(
        id="q", **BASICS, sequence=[{"id": str(i), "text": t} for i, t in enumerate(texts)]
    )


def test_ordering_items_must_differ():
    with pytest.raises(ValidationError, match=re.escape("duplicate item texts: ['b']")):
        ordering("a", "b", "b")


def test_an_ordering_response_must_place_every_item_once():
    q = ordering("a", "b", "c")
    q.check_response(OrderResponse(item_ids=["2", "0", "1"]))
    for ids in (["0", "1"], ["0", "1", "1"], ["0", "1", "9"]):
        with pytest.raises(ValueError, match="needs every item placed exactly once"):
            q.check_response(OrderResponse(item_ids=ids))


def matching(*pairs: tuple[str, str]) -> Matching:
    return Matching(
        id="q",
        **BASICS,
        pairs=[
            {"id": str(i), "left": left, "right": right} for i, (left, right) in enumerate(pairs)
        ],
    )


def test_matching_sides_must_differ():
    with pytest.raises(ValidationError, match=re.escape("duplicate right sides: ['x']")):
        matching(("a", "x"), ("b", "x"))


def test_a_matching_response_must_match_every_item_once():
    q = matching(("a", "x"), ("b", "y"))
    q.check_response(MatchResponse(matches={"0": "1", "1": "0"}))
    for matches in ({"0": "0"}, {"0": "1", "1": "1"}, {"0": "0", "1": "9"}):
        with pytest.raises(ValueError, match="needs every item matched exactly once"):
            q.check_response(MatchResponse(matches=matches))


# Lessons


def lesson(
    syllabus_id: str | None = None, tags: tuple[str, ...] = (), items: list | None = None
) -> Lesson:
    return Lesson(
        id="les_1",
        title="Placement",
        purpose="placement" if syllabus_id is None else "lesson",
        syllabus_id=syllabus_id,
        unit_id=None if syllabus_id is None else "u1",
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
        Lesson(
            id="les", title="t", purpose="lesson", syllabus_id="syl_1", unit_id="u1", items=[card()]
        )


def test_placement_has_no_teach_cards():
    with pytest.raises(ValidationError, match=re.escape("has no teach cards: ['c1']")):
        Lesson(id="les", title="t", purpose="placement", items=[card(), choice("q1")])


def test_a_lesson_needs_a_syllabus_and_unit():
    with pytest.raises(ValidationError, match="a lesson needs a syllabus_id"):
        Lesson(id="les", title="t", purpose="lesson", unit_id="u1", items=[choice("q1")])
    with pytest.raises(ValidationError, match="a lesson needs the unit_id"):
        Lesson(id="les", title="t", purpose="lesson", syllabus_id="syl_1", items=[choice("q1")])


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


def test_a_word_bank_needs_a_wrong_word():
    lesson(items=[fill_blank(word_bank=["2", "1", "3"])]).check_giveaways()
    with pytest.raises(ValueError, match="'q''s word bank needs a few wrong words too"):
        lesson(items=[fill_blank(word_bank=["2", "1"])]).check_giveaways()


def test_a_typed_answer_may_not_be_given_away_in_its_prompt():
    prompt = "Boots theory is named after what economic Unfairness? (socio-economic ___)"
    text_match = TextMatch(
        id="q", **(BASICS | {"prompt": prompt}), accepted=["class", "unfairness"]
    )
    with pytest.raises(ValueError, match="'q' gives its answer 'unfairness' away in the prompt"):
        lesson(items=[text_match]).check_giveaways()

    blank = FillBlank(
        id="q",
        **(BASICS | {"prompt": "Vampires come from uberwald."}),
        text="They come from ___.",
        blanks=[{"accepted": ["Überwald"]}],
    )
    with pytest.raises(ValueError, match="'q' gives its answer 'Überwald' away in the prompt"):
        lesson(items=[blank]).check_giveaways()


def test_every_giveaway_is_reported_at_once():
    banks = [fill_blank(word_bank=["2", "1"]).model_copy(update={"id": i}) for i in ("q1", "q2")]
    with pytest.raises(ValueError, match="'q1''s word bank .*; question 'q2''s word bank"):
        lesson(items=banks).check_giveaways()


def test_part_of_a_word_or_the_rest_of_the_line_isnt_a_giveaway():
    guards = TextMatch(id="q1", **(BASICS | {"prompt": "Which Guardsmen?"}), accepted=["Guards"])
    code = fill_blank(text="for name in names: print(___)", answers=("name",))
    lesson(items=[guards, code]).check_giveaways()


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
        BlanksResponse(values=["x", "y"]),
        OrderResponse(item_ids=["b", "a"]),
        MatchResponse(matches={"a": "b", "b": "a"}),
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
        unit_id="u1",
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
        ({"q1": SKIPPED, "q2": Answer(response=None, correct=True)}, "no answer, so can't be"),
    ],
    ids=["missing", "unknown", "wrong-kind", "unanswered-but-right"],
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
        "- q4: wrong, said they didn't know",
        "- q5: right",
    ]


def test_describe_attempt_shows_the_newer_question_types_in_words():
    lesson = Lesson(
        id="les_1",
        title="Mixed",
        purpose="lesson",
        syllabus_id="syl_1",
        unit_id="u1",
        items=[
            fill_blank().model_copy(update={"id": "q1"}),
            ordering("boil", "pour").model_copy(update={"id": "q2"}),
            matching(("cat", "chat"), ("dog", "chien")).model_copy(update={"id": "q3"}),
        ],
    )
    sent = attempt(
        q1=wrong(BlanksResponse(values=["1", "3"])),
        q2=wrong(OrderResponse(item_ids=["1", "0"])),
        q3=wrong(MatchResponse(matches={"0": "1", "1": "0"})),
    )
    graded = GradedAttempt(attempt=sent, number=1, results=check_attempt(lesson, sent))
    assert describe_attempt(lesson, graded).splitlines()[1:] == [
        "- q1: wrong, answered '1', '3'",
        "- q2: wrong, answered 'pour' → 'boil'",
        "- q3: wrong, answered 'cat' → 'chien'; 'dog' → 'chat'",
    ]
