"""The learner's path through a syllabus: each unit's lessons, as stops along the way.

The plan says how many lessons each unit takes, so the whole path is known from the start,
as in Duolingo. Lessons are written a stop at a time, and the topic is finished when every
stop has a lesson and every lesson has been taken.
"""

from __future__ import annotations

from dataclasses import dataclass

from pupil_server.learning.lesson import Lesson
from pupil_server.learning.syllabus import Syllabus, Unit


@dataclass(frozen=True)
class PathUnit:
    unit: Unit
    lessons: list[Lesson]
    """The unit's lessons, oldest first."""

    @property
    def stops(self) -> int:
        # A revision can give a unit fewer lessons than it already has; those stay.
        return max(self.unit.lessons, len(self.lessons))


@dataclass(frozen=True)
class Stop:
    """A stop without a lesson yet: lesson `number` of `of` in `unit`."""

    unit: Unit
    number: int
    of: int


def path(syllabus: Syllabus, lessons: list[Lesson]) -> list[PathUnit]:
    """The syllabus's units in learning order, each with its lessons. Lessons of units no
    longer in the syllabus are left off."""
    units = [PathUnit(u, []) for u in syllabus.units_in_order()]
    by_id = {p.unit.id: p for p in units}
    for lesson in lessons:
        if lesson.unit_id in by_id:
            by_id[lesson.unit_id].lessons.append(lesson)
    return units


def next_stop(units: list[PathUnit]) -> Stop | None:
    """The first stop along the path without a lesson, or None when every stop has one."""
    for p in units:
        if len(p.lessons) < p.stops:
            return Stop(p.unit, len(p.lessons) + 1, p.stops)
    return None
