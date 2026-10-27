"""OpenAI Codex backend, through the `openai-codex` SDK (which drives `codex app-server`).

App tools reach Codex from the loopback MCP bridge. Codex keeps its login and its config in
one place ($CODEX_HOME, ~/.codex by default), so runs use the learner's own login, and
everything else in their config that could reach a run is switched off for it: shell,
plugins, apps and other agent features, their MCP servers, and the turn-end `notify` hook.
The sandbox is read-only and nothing is ever approved, except the app's own tools.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

from openai_codex import (
    ApprovalMode,
    AsyncCodex,
    AsyncThread,
    AsyncTurnHandle,
    CodexConfig,
    Sandbox,
)
from openai_codex.types import ReasoningEffort

from pupil_server.agents.base import (
    AgentConfig,
    AgentError,
    AgentEvent,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnComplete,
    check_capabilities,
)
from pupil_server.agents.mcp_bridge import McpBridge
from pupil_server.settings import pupil_home

SERVER = "pupil"
# Codex has no aliases; the first model its model list recommends, as of October 2026.
DEFAULT_MODEL = "gpt-6.1-sol"

# Codex features that give the agent tools or act on the machine; a run needs none of them.
FEATURES_OFF = (
    "apps",
    "browser_use",
    "browser_use_external",
    "computer_use",
    "goals",
    "hooks",
    "image_generation",
    "in_app_browser",
    "memories",
    "multi_agent",
    "plugins",
    "remote_plugin",
    "shell_tool",
    "skill_search",
    "sleep_tool",
    "tool_suggest",
    "unified_exec",
    "view_image",
    "worktrees",
)


def default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def user_mcp_servers(codex_home: Path) -> list[str]:
    """The MCP servers the learner's own Codex config sets up."""
    path = codex_home / "config.toml"
    if not path.is_file():
        return []
    return list(tomllib.loads(path.read_text(encoding="utf-8")).get("mcp_servers", {}))


def launch_overrides(mcp_url: str, web_search: bool, codex_home: Path) -> tuple[str, ...]:
    """`-c` overrides for a run's Codex: the app's tools, and nothing of the user's."""
    return (
        *(f"features.{name}=false" for name in FEATURES_OFF),
        *(f"mcp_servers.{name}.enabled=false" for name in user_mcp_servers(codex_home)),
        f'web_search="{"live" if web_search else "disabled"}"',
        "notify=[]",
        "project_doc_max_bytes=0",
        'history.persistence="none"',
        f'mcp_servers.{SERVER}.url="{mcp_url}"',
        # With approvals off, Codex refuses MCP tools that aren't approved up front.
        f'mcp_servers.{SERVER}.default_tools_approval_mode="approve"',
        f"mcp_servers.{SERVER}.required=true",
        f"mcp_servers.{SERVER}.tool_timeout_sec=300",
    )


def translate(
    method: str, payload: dict[str, Any], usage: Any = None, model: str | None = None
) -> list[AgentEvent]:
    """One app-server notification as app events. `usage` (the latest token usage) and
    `model` are for the turn's end; Codex reports no cost."""
    if method == "item/agentMessage/delta":
        return [TextDelta(text=payload["delta"])]
    if method in ("item/started", "item/completed"):
        item = payload["item"]
        if item["type"] == "mcpToolCall" and item["server"] == SERVER:
            if method == "item/started":
                return [ToolCall(id=item["id"], name=item["tool"], input=item["arguments"] or {})]
            content = (item.get("result") or {}).get("content") or []
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            output = "".join(texts) if len(texts) == len(content) else content
            if item.get("error"):
                output = item["error"].get("message") or output
            return [
                ToolResult(id=item["id"], output=output, is_error=item["status"] != "completed")
            ]
        if item["type"] == "webSearch" and method == "item/completed":
            return [ToolCall(id=item["id"], name="web_search", input={"query": item["query"]})]
        return []
    if method == "turn/completed":
        turn = payload["turn"]
        if turn["status"] == "completed":
            return [TurnComplete(cost_usd=None, usage=usage, model=model)]
        error = (turn.get("error") or {}).get("message")
        return [AgentError(message=error or f"the turn was {turn['status']}")]
    return []


async def run_turn(
    notifications: AsyncIterator[tuple[str, dict[str, Any]]],
    interrupt: Callable[[], Awaitable[Any]],
    max_turns: int | None,
    model: str | None = None,
) -> AsyncIterator[AgentEvent]:
    """A turn's notifications as app events, stopping it once it makes more tool calls than
    `max_turns` (Codex has no limit of its own)."""
    usage = None
    calls = 0
    stopped = False
    async for method, payload in notifications:
        if method == "thread/tokenUsage/updated":
            usage = payload["tokenUsage"]["total"]
            continue
        for event in translate(method, payload, usage, model):
            if stopped:
                continue  # until the interrupted turn ends
            if isinstance(event, ToolCall):
                calls += 1
                if max_turns is not None and calls > max_turns:
                    stopped = True
                    await interrupt()
                    continue
            yield event
    if stopped:
        yield AgentError(message=f"went past the limit of tool calls ({max_turns})")


async def _notifications(turn: AsyncTurnHandle) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    async for n in turn.stream():
        dump = getattr(n.payload, "model_dump", None)
        yield n.method, (dump(mode="json", by_alias=True) if dump else {})


class CodexSession:
    def __init__(
        self,
        codex: AsyncCodex,
        thread: AsyncThread,
        bridge: McpBridge,
        url: str,
        config: AgentConfig,
    ) -> None:
        self._codex = codex
        self._thread = thread
        self._bridge = bridge
        self._url = url
        self._max_turns = config.max_turns
        self._model = config.model or DEFAULT_MODEL
        self._effort = None if config.effort is None else ReasoningEffort(config.effort)
        self._turn: AsyncTurnHandle | None = None

    async def send(self, text: str) -> AsyncIterator[AgentEvent]:
        self._turn = turn = await self._thread.turn(text, effort=self._effort)
        notifications = _notifications(turn)
        async for event in run_turn(notifications, turn.interrupt, self._max_turns, self._model):
            yield event

    async def interrupt(self) -> None:
        if self._turn is not None:
            await self._turn.interrupt()

    async def close(self) -> None:
        self._bridge.unregister(self._url)
        await self._codex.close()


class CodexBackend:
    name = "codex"
    supports_web_search = True

    def __init__(self, workdir: Path | None = None, codex_home: Path | None = None) -> None:
        # Where Codex runs: an empty folder, so there's no project for it to read.
        self._workdir = workdir or pupil_home() / "agent-codex"
        self._codex_home = codex_home or default_codex_home()
        self._bridge = McpBridge()

    async def open_session(self, config: AgentConfig) -> CodexSession:
        check_capabilities(self, config)
        self._workdir.mkdir(parents=True, exist_ok=True)
        url = await self._bridge.register(config.tools)
        overrides = launch_overrides(url, config.web_search, self._codex_home)
        codex = AsyncCodex(CodexConfig(config_overrides=overrides, cwd=str(self._workdir)))
        try:
            thread = await codex.thread_start(
                # Replaces Codex's own coding-agent instructions, as Claude's system prompt does.
                base_instructions=config.system_prompt,
                model=config.model or DEFAULT_MODEL,
                sandbox=Sandbox.read_only,
                approval_mode=ApprovalMode.deny_all,
                ephemeral=True,
                cwd=str(self._workdir),
            )
        except BaseException:
            self._bridge.unregister(url)
            await codex.close()
            raise
        return CodexSession(codex, thread, self._bridge, url, config)

    async def close(self) -> None:
        await self._bridge.close()
