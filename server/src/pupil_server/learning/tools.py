"""Agent tools for planning and assessing: syllabi, quizzes and the learner's answers.

The agent writes syllabi and quizzes, but never grades: it passes on what the learner answered
and the code says what was right. Bad input comes back to the agent as an error result naming
the problem, so it can correct itself.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pupil_server.agents.base import Tool, tool
from pupil_server.db import Database, new_id
from pupil_server.db.learning import (
    AttemptRepo,
    EvidenceRepo,
    QuizRepo,
    StaleRevision,
    SyllabusRepo,
)
from pupil_server.learning.quiz import Question, Quiz, QuizAttempt, Response
from pupil_server.learning.syllabus import Objective, Syllabus, Unit, objective_changes

OBJECTIVE_ID_RULE = (
    "The learner's progress is recorded against objective ids, so an objective keeps its id "
    "for as long as it is the same skill, however it is worded."
)

# Field docstrings become descriptions in the schema the agent sees, and unknown fields are
# refused rather than ignored, so the agent can't believe it set something it didn't.
_CONFIG = ConfigDict(use_attribute_docstrings=True, extra="forbid")


class _Input(BaseModel):
    model_config = _CONFIG


class NewObjective(_Input):
    text: str = Field(min_length=1)
    """One thing the learner should be able to do."""


class RevisedObjective(NewObjective):
    id: str | None = None
    """The objective's current id, copied from get_syllabus, even if you reword it. Leave out
    for a new skill, and an id is assigned."""


class NewUnit(Unit):
    model_config = _CONFIG

    objectives: list[NewObjective] = Field(min_length=1)  # type: ignore[assignment]
    """Ids are assigned when the syllabus is created."""


class RevisedUnit(Unit):
    model_config = _CONFIG

    objectives: list[RevisedObjective] = Field(min_length=1)  # type: ignore[assignment]


class SyllabusPlan(_Input):
    topic: str
    goal: str
    """What the learner wants to be able to do by the end."""
    units: list[NewUnit] = Field(min_length=1)
    """Unit ids are short slugs, unique within the syllabus."""


class SyllabusChange(_Input):
    syllabus_id: str
    based_on_revision: int
    """The revision this change was made from, as get_syllabus returned it."""
    topic: str
    goal: str
    units: list[RevisedUnit] = Field(min_length=1)
    retired_objectives: list[str] = Field(default_factory=list)
    """Ids of objectives dropped because the learner no longer needs that skill. Required for
    any dropped objective the learner has progress on."""


class SyllabusRef(_Input):
    syllabus_id: str
    revision: int | None = None
    """A past revision to read; leave out for the current one."""


class NoArgs(_Input):
    pass


class QuizPlan(_Input):
    title: str
    purpose: Literal["placement", "checkpoint"]
    """placement: find the learner's level, usually before a syllabus exists. checkpoint: check
    what they learned from a syllabus."""
    syllabus_id: str | None = None
    """Required for a checkpoint. With it, every question must list the objective ids it tests;
    without it, questions list none."""
    questions: list[Question] = Field(min_length=1)


class Answers(_Input):
    quiz_id: str
    responses: dict[str, Response]
    """Question id to the learner's answer, exactly as they gave it. Leave out skipped
    questions; they count as wrong."""


def _units(units: list[NewUnit] | list[RevisedUnit]) -> list[Unit]:
    """Units with an id for every objective, new ones getting a fresh one."""
    return [
        Unit(
            **u.model_dump(exclude={"objectives"}),
            objectives=[
                Objective(id=getattr(o, "id", None) or new_id("obj"), text=o.text)
                for o in u.objectives
            ],
        )
        for u in units
    ]


def learning_tools(db: Database, learner_id: str) -> list[Tool]:
    """The tools, acting for one learner."""
    syllabi, quizzes, attempts = SyllabusRepo(db), QuizRepo(db), AttemptRepo(db)
    evidence = EvidenceRepo(db)

    @tool(
        "create_syllabus",
        "Create a learning plan for a topic: units of objectives, each unit listing the units "
        "to learn first. Returns the syllabus with the ids given to its objectives. "
        + OBJECTIVE_ID_RULE,
    )
    async def create_syllabus(plan: SyllabusPlan) -> dict[str, Any]:
        syllabus = Syllabus(
            id=new_id("syl"), topic=plan.topic, goal=plan.goal, units=_units(plan.units)
        )
        stored = await syllabi.create(learner_id, syllabus)
        return {"syllabus": stored.model_dump(mode="json")}

    @tool(
        "revise_syllabus",
        "Replace a syllabus with a changed version, kept as its next revision. Send the whole "
        "syllabus, not just the changes, and the revision you based it on; if it has changed "
        "since, read it again and redo the change. Keep each objective's id for as long as it "
        "is the same skill, and leave the id out for a new skill. Returns the syllabus and what "
        "changed. " + OBJECTIVE_ID_RULE,
    )
    async def revise_syllabus(change: SyllabusChange) -> dict[str, Any]:
        current = await syllabi.get(learner_id, change.syllabus_id)
        if change.based_on_revision != current.revision:
            # Checked again when storing; checked here so the checks below compare the right
            # revisions.
            raise StaleRevision(
                f"syllabus {current.id!r} is at revision {current.revision}, but this change "
                f"is based on revision {change.based_on_revision}"
            )
        current_ids = current.objective_ids()
        kept = [o.id for u in change.units for o in u.objectives if o.id is not None]
        unknown = [i for i in [*kept, *change.retired_objectives] if i not in current_ids]
        if unknown:
            raise ValueError(
                f"objective ids not in revision {current.revision}: {unknown}. Copy ids from "
                "get_syllabus, or leave the id out for a new skill."
            )
        still_there = [i for i in change.retired_objectives if i in kept]
        if still_there:
            raise ValueError(f"retired objectives are still in the syllabus: {still_there}")

        syllabus = Syllabus(
            id=change.syllabus_id,
            topic=change.topic,
            goal=change.goal,
            units=_units(change.units),
            revision=change.based_on_revision,
        )
        changes = objective_changes(current, syllabus)
        practised = {e.objective_id for e in await evidence.for_syllabus(learner_id, current.id)}
        unretired = [
            o
            for o in changes.removed
            if o.id in practised and o.id not in change.retired_objectives
        ]
        if unretired:
            dropped = ", ".join(f"{o.id} ({o.text!r})" for o in unretired)
            raise ValueError(
                f"the learner has progress on objectives missing from this revision: {dropped}. "
                "Keep an objective's id if it is the same skill reworded, or list it in "
                "retired_objectives if the learner no longer needs it."
            )

        stored = await syllabi.revise(learner_id, syllabus)
        warnings = [
            f"{r.id} has the learner's progress and was reworded from {r.before!r} to "
            f"{r.after!r}. If it is no longer the same skill, revise again: retire {r.id} and "
            "add the new skill without an id."
            for r in changes.reworded
            if r.id in practised
        ]
        return {
            "syllabus": stored.model_dump(mode="json"),
            "changes": changes.model_dump(mode="json"),
            "warnings": warnings,
        }

    @tool("get_syllabus", "Read a syllabus: its current revision, or a past one.")
    async def get_syllabus(ref: SyllabusRef) -> dict[str, Any]:
        stored = await syllabi.get(learner_id, ref.syllabus_id, ref.revision)
        return stored.model_dump(mode="json")

    @tool("list_syllabi", "List the learner's syllabi, oldest first.")
    async def list_syllabi(_: NoArgs) -> dict[str, Any]:
        return {
            "syllabi": [
                {"syllabus_id": s.id, "topic": s.topic, "goal": s.goal, "revision": s.revision}
                for s in await syllabi.list_latest(learner_id)
            ]
        }

    @tool(
        "create_quiz",
        "Create a quiz that code will grade, so every question needs an exact answer. Returns "
        "the quiz id. Show the learner the questions, not the answers.",
    )
    async def create_quiz(plan: QuizPlan) -> dict[str, Any]:
        quiz = Quiz(
            id=new_id("quiz"),
            title=plan.title,
            purpose=plan.purpose,
            syllabus_id=plan.syllabus_id,
            questions=plan.questions,
        )
        await quizzes.create(learner_id, quiz)
        return {"quiz_id": quiz.id}

    @tool(
        "submit_quiz_answers",
        "Grade the learner's answers to a quiz and record them. Send their answers as given, "
        "even wrong ones; never correct them first. Returns which questions were right.",
    )
    async def submit_quiz_answers(answers: Answers) -> dict[str, Any]:
        attempt = QuizAttempt(
            id=new_id("att"),
            quiz_id=answers.quiz_id,
            responses=answers.responses,
            submitted_at=datetime.now(UTC),
        )
        results = await attempts.submit(learner_id, attempt)
        return {
            "attempt_id": attempt.id,
            "correct": sum(r.correct for r in results),
            "total": len(results),
            "results": [{"question_id": r.question_id, "correct": r.correct} for r in results],
        }

    return [
        create_syllabus,
        revise_syllabus,
        get_syllabus,
        list_syllabi,
        create_quiz,
        submit_quiz_answers,
    ]
