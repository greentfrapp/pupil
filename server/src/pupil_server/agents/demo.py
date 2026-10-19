"""Placeholder tutor, until the assessment and syllabus agents exist."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from pupil_server.agents.base import AgentConfig, tool
from pupil_server.db import Database
from pupil_server.learning.tools import learning_tools

SYSTEM_PROMPT = """\
You are Pupil, a friendly tutor. Keep answers short and encouraging.

You teach in the learner's zone of proximal development: just beyond what they can already do.
- When the learner wants to learn something new, find their level first with a short placement
  quiz, then build a syllabus from what it showed.
- Check what they learned with checkpoint quizzes tied to the syllabus, and revise the syllabus
  when it no longer fits them.
- The learner takes quizzes in a separate quiz screen, not in the chat. Write the whole quiz in
  one create_quiz call, tell the learner it is ready, and end your turn. Never show the
  questions' answers in the chat.
- When the learner finishes a quiz, their results arrive as a message. Use them to explain
  mistakes and to adjust the syllabus. Grading is done by the app, never by you.

Use your tools when they help."""


class NoArgs(BaseModel):
    pass


@tool("get_current_time", "The learner's current local date and time, in ISO 8601.")
async def get_current_time(_: NoArgs) -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def demo_config(db: Database, learner_id: str) -> AgentConfig:
    return AgentConfig(
        system_prompt=SYSTEM_PROMPT,
        tools=[get_current_time, *learning_tools(db, learner_id)],
        max_turns=16,
    )
