import re

import pytest
from pydantic import ValidationError

from pupil_server.learning.syllabus import Syllabus


def unit(uid: str, *prerequisites: str, objectives: tuple[str, ...] | None = None) -> dict:
    return {
        "id": uid,
        "title": uid.title(),
        "summary": "",
        "objectives": [{"id": o, "text": o} for o in (objectives or (f"obj_{uid}",))],
        "prerequisites": list(prerequisites),
    }


def syllabus(*units: dict) -> Syllabus:
    return Syllabus(id="syl_1", topic="Python", goal="Write small scripts", units=list(units))


def test_valid_syllabus():
    s = syllabus(unit("basics"), unit("loops", "basics"), unit("functions", "basics"))
    assert s.revision == 1
    assert s.objective_ids() == {"obj_basics", "obj_loops", "obj_functions"}


@pytest.mark.parametrize(
    ("units", "message"),
    [
        ([unit("a"), unit("a", objectives=("x",))], "duplicate unit ids: ['a']"),
        (
            [unit("a", objectives=("o1",)), unit("b", objectives=("o1", "o2"))],
            "duplicate objective ids: ['o1']",
        ),
        ([unit("a", "ghost")], "unit 'a' has unknown prerequisites: ['ghost']"),
        ([unit("a", "a")], "prerequisite cycle: a -> a"),
        ([unit("a", "c"), unit("b", "a"), unit("c", "b")], "prerequisite cycle: a -> c -> b -> a"),
    ],
    ids=["duplicate-unit", "duplicate-objective", "unknown-prerequisite", "self-cycle", "cycle"],
)
def test_invalid_structure_names_the_offending_ids(units, message):
    with pytest.raises(ValidationError, match=re.escape(message)):
        syllabus(*units)


def test_unit_needs_an_objective():
    bad = unit("a")
    bad["objectives"] = []
    with pytest.raises(ValidationError):
        syllabus(bad)


def test_units_in_order_puts_prerequisites_first_and_keeps_authored_order():
    s = syllabus(
        unit("functions", "basics"),
        unit("basics"),
        unit("files"),
        unit("classes", "functions"),
    )
    assert [u.id for u in s.units_in_order()] == ["basics", "functions", "files", "classes"]
