"""Agent tools for planning and teaching: syllabi and lessons.

The agent writes syllabi and lessons, but never grades or relays answers: the learner answers
in the app's lesson player, which grades them, and the agent reads the results when it needs
them. Bad input comes back to the agent as an error result naming the problem, so it
can correct itself.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pupil_server.agents.base import Tool, tool
from pupil_server.db import Database, new_id
from pupil_server.db.learning import (
    AttemptRepo,
    EvidenceRepo,
    LessonRepo,
    StaleRevision,
    SyllabusRepo,
)
from pupil_server.db.topics import TopicRepo
from pupil_server.learning.lesson import Item, Lesson, describe_attempt
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
    rationale: str = Field(min_length=1, max_length=200)
    """One line for the learner on why the plan looks the way it does, e.g. 'Exam-focused, 6
    units, starting from functions since you know the basics.' Shown with the plan."""
    units: list[NewUnit] = Field(min_length=1)
    """Unit ids are short slugs, unique within the syllabus."""


class SyllabusChange(_Input):
    syllabus_id: str
    based_on_revision: int
    """The revision this change was made from, as get_syllabus returned it."""
    topic: str
    goal: str
    rationale: str = Field(min_length=1, max_length=200)
    """One line for the learner on why the plan looks the way it does, e.g. 'Exam-focused, 6
    units, starting from functions since you know the basics.' Shown with the plan; update
    it if the change alters why."""
    units: list[RevisedUnit] = Field(min_length=1)
    retired_objectives: list[str] = Field(default_factory=list)
    """Ids of objectives dropped because the learner no longer needs that skill. Required for
    any dropped objective the learner has progress on."""


class SyllabusRef(_Input):
    syllabus_id: str
    revision: int | None = None
    """A past revision to read; leave out for the current one."""


class LessonPlan(_Input):
    title: str
    purpose: Literal["placement", "lesson"]
    """placement: find the learner's level, usually before a syllabus exists; no teach cards,
    and it can't be retried. lesson: teach objectives from a syllabus."""
    syllabus_id: str | None = None
    """Required for a lesson. With it, every question must list the objective ids it tests;
    without it, questions list none."""
    keep_order: bool = False
    """Set when the questions build on each other. Otherwise they are shuffled each time the
    lesson is taken, though never past a teach card."""
    items: list[Item] = Field(min_length=1)
    """Questions, and teach cards before the questions that use them. Item ids are short and
    unique within the lesson."""


class RecentResults(_Input):
    limit: int = Field(default=5, ge=1, le=20)
    """How many of the latest attempts to read."""


class LessonRef(_Input):
    lesson_id: str


class NewNote(_Input):
    text: str = Field(min_length=1, max_length=500)
    """One thing worth remembering about the learner, in a sentence."""


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


def learning_tools(db: Database, learner_id: str, topic_id: str) -> list[Tool]:
    """The tools for a run on one of the learner's topics: what they create is filed under the
    topic, and the results they read are the topic's."""
    syllabi, lessons, evidence = SyllabusRepo(db), LessonRepo(db), EvidenceRepo(db)
    attempts, topics = AttemptRepo(db), TopicRepo(db)

    @tool(
        "create_syllabus",
        "Create a learning plan for a topic: units of objectives, each unit listing the units "
        "to learn first. Returns the syllabus with the ids given to its objectives. "
        + OBJECTIVE_ID_RULE,
    )
    async def create_syllabus(plan: SyllabusPlan) -> dict[str, Any]:
        syllabus = Syllabus(
            id=new_id("syl"),
            topic=plan.topic,
            goal=plan.goal,
            rationale=plan.rationale,
            units=_units(plan.units),
        )
        stored = await syllabi.create(learner_id, syllabus, topic_id)
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
            rationale=change.rationale,
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

    @tool(
        "create_lesson",
        "Create a short lesson that teaches mostly by asking: 8 to 12 questions, or 10 to 15 "
        "from easy to hard for placement. The app grades it, so every question needs an exact "
        "answer. Mix question types, favouring ones where the learner has to produce or arrange "
        "the answer (fill_blank, text_match, ordering, matching) over true/false and multiple "
        "choice. "
        "Teach inside the questions where you can, "
        "e.g. 'In Python, // divides and rounds down. What is 7 // 2?'. Add a teach card only "
        "before a brand-new idea, and rarely. After each answer the learner sees whether they "
        "were right, the correct answer and the explanation, so keep explanations to a "
        "sentence or two. Write the whole lesson in this one call. The learner takes it in the "
        "app's lesson player, so don't repeat its questions or answers in your reply. Read how "
        "they did with recent_results.",
    )
    async def create_lesson(plan: LessonPlan) -> dict[str, Any]:
        lesson = Lesson(id=new_id("les"), **plan.model_dump())
        await lessons.create(learner_id, lesson, topic_id)
        return {"lesson_id": lesson.id}

    @tool("get_lesson", "Read a past lesson in full: its questions and their answers.")
    async def get_lesson(ref: LessonRef) -> dict[str, Any]:
        return (await lessons.get(learner_id, ref.lesson_id)).model_dump(mode="json")

    @tool(
        "add_note",
        "Write down something about the learner worth remembering in later runs, e.g. "
        "'prefers real-world examples' or 'keeps confusing joins and unions'. You won't "
        "remember anything else from this run.",
    )
    async def add_note(note: NewNote) -> dict[str, Any]:
        await topics.add_note(learner_id, topic_id, note.text)
        return {"saved": True}

    @tool(
        "recent_results",
        "Read how the learner did in their latest lesson attempts, newest first: their score, "
        "and what they answered for each question they got wrong. A lesson can be retried, so "
        "each attempt says which attempt at the lesson it was.",
    )
    async def recent_results(ask: RecentResults) -> dict[str, Any]:
        described = []
        for graded in await attempts.recent(learner_id, ask.limit, topic_id):
            lesson = await lessons.get(learner_id, graded.attempt.lesson_id)
            described.append(
                {
                    "submitted_at": graded.attempt.submitted_at.isoformat(),
                    "summary": describe_attempt(lesson, graded),
                }
            )
        return {"attempts": described}

    return [
        create_syllabus,
        revise_syllabus,
        get_syllabus,
        create_lesson,
        get_lesson,
        recent_results,
        add_note,
    ]
