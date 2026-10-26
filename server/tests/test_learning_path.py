from pupil_server.learning.lesson import Lesson, TrueFalse
from pupil_server.learning.path import next_stop, path
from pupil_server.learning.syllabus import Syllabus


def syllabus(**lessons: int) -> Syllabus:
    """Units in the order given, each needing the one before, with these many lessons."""
    ids = list(lessons)
    units = [
        {
            "id": uid,
            "title": uid,
            "summary": "",
            "objectives": [{"id": f"o_{uid}", "text": "t"}],
            "prerequisites": ids[i - 1 : i],
            "lessons": n,
        }
        for i, (uid, n) in enumerate(lessons.items())
    ]
    return Syllabus(id="syl_1", topic="t", goal="g", units=units)


def lesson(lid: str, unit_id: str) -> Lesson:
    question = TrueFalse(
        id="q1", prompt="p", difficulty=1, explanation="e", answer=True, objective_ids=["o_a"]
    )
    return Lesson(
        id=lid, title=lid, purpose="lesson", syllabus_id="syl_1", unit_id=unit_id, items=[question]
    )


def test_lessons_go_under_their_units_and_the_next_stop_follows_them():
    units = path(syllabus(a=2, b=1), [lesson("les_1", "a"), lesson("les_2", "a")])
    assert [(p.unit.id, [x.id for x in p.lessons]) for p in units] == [
        ("a", ["les_1", "les_2"]),
        ("b", []),
    ]
    stop = next_stop(units)
    assert (stop.unit.id, stop.number, stop.of) == ("b", 1, 1)


def test_the_path_ends_when_every_stop_has_a_lesson():
    assert next_stop(path(syllabus(a=1), [lesson("les_1", "a")])) is None


def test_a_unit_cut_below_its_lessons_keeps_them():
    [unit] = path(syllabus(a=1), [lesson("les_1", "a"), lesson("les_2", "a")])
    assert unit.stops == 2


def test_lessons_of_units_no_longer_in_the_syllabus_are_left_off():
    [unit] = path(syllabus(a=1), [lesson("les_1", "gone")])
    assert unit.lessons == []
