"""Placeholder tutor, until the assessment and syllabus agents exist."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from pupil_server.agents.base import AgentConfig, tool


class NoArgs(BaseModel):
    pass


@tool("get_current_time", "The learner's current local date and time, in ISO 8601.")
async def get_current_time(_: NoArgs) -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def demo_config() -> AgentConfig:
    return AgentConfig(
        system_prompt=(
            "You are Pupil, a friendly tutor. Keep answers short and encouraging. "
            "Use your tools when they help."
        ),
        tools=[get_current_time],
        max_turns=8,
    )
