"""A syllabus: the roadmap for learning one topic.

It is only the plan. What the learner knows lives in `progress`, keyed by objective id, so the
plan can be revised without losing that. Objective ids must therefore stay stable: a reworded
skill keeps its id, a different skill gets a new one.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Objective(BaseModel):
    """One thing the learner should be able to do; lesson questions are tagged with these ids."""

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class Unit(BaseModel):
    # Field docstrings become descriptions in the schema an agent sees.
    model_config = ConfigDict(use_attribute_docstrings=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str
    objectives: list[Objective] = Field(min_length=1)
    prerequisites: list[str] = Field(default_factory=list)
    """Ids of units to learn before this one."""
    estimated_minutes: int | None = Field(default=None, gt=0)


class Syllabus(BaseModel):
    id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    """What the learner wants to be able to do by the end."""
    rationale: str | None = None
    """Why the plan looks the way it does, in a line for the learner."""
    units: list[Unit] = Field(min_length=1)
    revision: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _check_structure(self) -> Syllabus:
        # Errors name the offending ids, so an agent can fix what it wrote.
        _reject_duplicates("unit", [u.id for u in self.units])
        _reject_duplicates("objective", [o.id for u in self.units for o in u.objectives])
        known = {u.id for u in self.units}
        for unit in self.units:
            unknown = [p for p in unit.prerequisites if p not in known]
            if unknown:
                raise ValueError(f"unit {unit.id!r} has unknown prerequisites: {unknown}")
        cycle = _find_cycle(self.units)
        if cycle:
            raise ValueError(
                f"prerequisite cycle: {' -> '.join(cycle)} (each unit requires the next)"
            )
        return self

    def units_in_order(self) -> list[Unit]:
        """Units with every prerequisite before its dependents, otherwise in authored order."""
        placed: set[str] = set()
        ordered: list[Unit] = []
        remaining = list(self.units)
        while remaining:
            # The validator rules out cycles, so some unit is always ready.
            unit = next(u for u in remaining if placed.issuperset(u.prerequisites))
            remaining.remove(unit)
            placed.add(unit.id)
            ordered.append(unit)
        return ordered

    def first_unit_with(self, objective_ids: Iterable[str]) -> Unit | None:
        """The earliest unit, in learning order, with any of these objectives."""
        wanted = set(objective_ids)
        return next(
            (u for u in self.units_in_order() if any(o.id in wanted for o in u.objectives)),
            None,
        )

    def objective_ids(self) -> set[str]:
        return {o.id for u in self.units for o in u.objectives}

    def objectives(self) -> dict[str, Objective]:
        return {o.id: o for u in self.units for o in u.objectives}


class Reworded(BaseModel):
    id: str
    before: str
    after: str


class ObjectiveChanges(BaseModel):
    """How the objectives differ between two revisions, matched by id."""

    added: list[Objective]
    reworded: list[Reworded]
    removed: list[Objective]


def objective_changes(before: Syllabus, after: Syllabus) -> ObjectiveChanges:
    old, new = before.objectives(), after.objectives()
    return ObjectiveChanges(
        added=[o for i, o in new.items() if i not in old],
        reworded=[
            Reworded(id=i, before=old[i].text, after=o.text)
            for i, o in new.items()
            if i in old and old[i].text != o.text
        ],
        removed=[o for i, o in old.items() if i not in new],
    )


def _reject_duplicates(kind: str, ids: list[str]) -> None:
    duplicates = sorted(i for i, n in Counter(ids).items() if n > 1)
    if duplicates:
        raise ValueError(f"duplicate {kind} ids: {duplicates}")


def _find_cycle(units: list[Unit]) -> list[str] | None:
    """A cycle as a path that ends where it starts, e.g. ['a', 'b', 'a'], or None."""
    requires = {u.id: u.prerequisites for u in units}
    done: set[str] = set()

    def visit(unit_id: str, path: list[str]) -> list[str] | None:
        if unit_id in path:
            return path[path.index(unit_id) :] + [unit_id]
        if unit_id in done:
            return None
        for prerequisite in requires[unit_id]:
            cycle = visit(prerequisite, [*path, unit_id])
            if cycle:
                return cycle
        done.add(unit_id)
        return None

    for unit in units:
        cycle = visit(unit.id, [])
        if cycle:
            return cycle
    return None
