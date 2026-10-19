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
from pupil_server.db.learning import AttemptRepo, QuizRepo, SyllabusRepo
from pupil_server.learning.quiz import Question, Quiz, QuizAttempt, Response
from pupil_server.learning.syllabus import Syllabus, Unit

OBJECTIVE_ID_RULE = (
    "Keep objective ids stable: the learner's progress is recorded against them. A reworded "
    "objective keeps its id; only a different skill gets a new one."
)


class _Input(BaseModel):
    # Field docstrings become descriptions in the schema the agent sees.
    model_config = ConfigDict(use_attribute_docstrings=True)


class SyllabusPlan(_Input):
    topic: str
    goal: str
    """What the learner wants to be able to do by the end."""
    units: list[Unit] = Field(min_length=1)
    """Unit and objective ids are short slugs, unique within the syllabus."""


class SyllabusChange(SyllabusPlan):
    syllabus_id: str
    based_on_revision: int
    """The revision this change was made from, as get_syllabus returned it."""


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


def learning_tools(db: Database, learner_id: str) -> list[Tool]:
    """The tools, acting for one learner."""
    syllabi, quizzes, attempts = SyllabusRepo(db), QuizRepo(db), AttemptRepo(db)

    @tool(
        "create_syllabus",
        "Create a learning plan for a topic: units of objectives, each unit listing the units "
        "to learn first. Returns the new syllabus id. " + OBJECTIVE_ID_RULE,
    )
    async def create_syllabus(plan: SyllabusPlan) -> dict[str, Any]:
        syllabus = Syllabus(id=new_id("syl"), topic=plan.topic, goal=plan.goal, units=plan.units)
        stored = await syllabi.create(learner_id, syllabus)
        return {"syllabus_id": stored.id, "revision": stored.revision}

    @tool(
        "revise_syllabus",
        "Replace a syllabus with a changed version, kept as its next revision. Send the whole "
        "syllabus, not just the changes, and the revision you based it on; if it has changed "
        "since, read it again and redo the change. " + OBJECTIVE_ID_RULE,
    )
    async def revise_syllabus(change: SyllabusChange) -> dict[str, Any]:
        syllabus = Syllabus(
            id=change.syllabus_id,
            topic=change.topic,
            goal=change.goal,
            units=change.units,
            revision=change.based_on_revision,
        )
        stored = await syllabi.revise(learner_id, syllabus)
        return {"syllabus_id": stored.id, "revision": stored.revision}

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
