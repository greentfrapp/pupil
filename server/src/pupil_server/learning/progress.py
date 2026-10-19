"""What the learner has shown they know, per syllabus objective.

Kept apart from the syllabus so revising the plan never loses it. Mastery is derived from the
evidence; the logic that does that comes later, so these are types only for now.
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field


class Evidence(BaseModel):
    """One graded answer that bears on one objective."""

    objective_id: str
    attempt_id: str
    question_id: str
    correct: bool
    at: AwareDatetime


Mastery = Literal["unknown", "learning", "mastered"]


class ObjectiveProgress(BaseModel):
    objective_id: str
    mastery: Mastery = "unknown"
    evidence: list[Evidence] = Field(default_factory=list)


class LearnerProgress(BaseModel):
    learner_id: str
    syllabus_id: str
    objectives: dict[str, ObjectiveProgress] = Field(default_factory=dict)
    """Objective id to progress; objectives with no evidence yet may be absent."""
