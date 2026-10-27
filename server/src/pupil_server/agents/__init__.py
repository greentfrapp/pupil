"""Agent layer: one contract (`base`), one adapter per runtime."""

from __future__ import annotations

from pupil_server.agents.base import (
    AgentBackend,
    AgentConfig,
    AgentError,
    AgentEvent,
    AgentSession,
    TextDelta,
    Tool,
    ToolCall,
    ToolResult,
    TurnComplete,
    UnsupportedCapability,
    tool,
)

__all__ = [
    "AgentBackend",
    "AgentConfig",
    "AgentError",
    "AgentEvent",
    "AgentSession",
    "TextDelta",
    "Tool",
    "ToolCall",
    "ToolResult",
    "TurnComplete",
    "UnsupportedCapability",
    "make_backend",
    "tool",
]


def make_backend(name: str) -> AgentBackend:
    """Build a backend by name, importing its runtime only when it is chosen."""
    if name == "claude":
        from pupil_server.agents.claude import ClaudeBackend

        return ClaudeBackend()
    if name == "codex":
        from pupil_server.agents.codex import CodexBackend

        return CodexBackend()
    if name == "fake":
        from pupil_server.agents.fake import FakeBackend

        return FakeBackend()
    raise ValueError(f"unknown agent backend {name!r}")
