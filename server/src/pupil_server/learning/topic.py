"""Topics: what the learner asked to learn, and their answers to the setup questions.

Everything made for a topic (its syllabus, lessons, notes and the agent's runs) points back at
it, so the topic itself never changes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

Why = Literal["work", "exam", "build", "curiosity"]
Depth = Literal["overview", "working", "expert"]
Level = Literal["new", "basics", "well"]


class Profile(BaseModel):
    """The learner's answers to the fixed setup questions."""

    why: Why
    """Why are you learning this?"""
    depth: Depth
    """How far do you want to go?"""
    level: Level
    """How much do you know already? Someone new to it skips placement."""
    specific: str | None = Field(default=None, max_length=300)
    """Anything specific, e.g. 'AP Calculus BC' or 'a Discord bot'."""


class Topic(BaseModel):
    id: str
    request: str
    """What the learner typed when they asked to learn it."""
    profile: Profile
    created_at: AwareDatetime


class Note(BaseModel):
    """Something the agent wrote down about the learner, to remember in later runs."""

    text: str
    created_at: AwareDatetime
