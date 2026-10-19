"""Claude Agent SDK backend.

App tools are served to Claude from an in-process MCP server. The agent is isolated from the
user's own Claude Code setup: no built-in tools beyond web search, no settings, CLAUDE.md or
other MCP servers, and nothing runs that was not allowed up front.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SdkMcpTool,
    StreamEvent,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
)

from pupil_server.agents.base import (
    AgentConfig,
    AgentError,
    AgentEvent,
    TextDelta,
    Tool,
    ToolCall,
    ToolResult,
    TurnComplete,
    check_capabilities,
)
from pupil_server.settings import pupil_home

SERVER = "pupil"
MCP_PREFIX = f"mcp__{SERVER}__"
WEB_TOOLS = {"WebSearch": "web_search", "WebFetch": "web_fetch"}


def _app_tool_name(name: str) -> str:
    """Claude's name for a tool, as the app knows it."""
    return WEB_TOOLS.get(name) or name.removeprefix(MCP_PREFIX)


def _flatten(content: Any) -> Any:
    """MCP tool content as plain text when it is all text, otherwise unchanged."""
    if isinstance(content, list) and all(
        isinstance(c, dict) and c.get("type") == "text" for c in content
    ):
        return "".join(c["text"] for c in content)
    return content


def translate(message: Any) -> list[AgentEvent]:
    """One SDK message as app events. Text comes only from stream deltas, never twice."""
    if isinstance(message, StreamEvent):
        event = message.event
        delta = event.get("delta") or {}
        if event.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
            return [TextDelta(text=delta["text"])]
        return []
    if isinstance(message, AssistantMessage):
        return [
            ToolCall(id=b.id, name=_app_tool_name(b.name), input=b.input)
            for b in message.content
            if isinstance(b, ToolUseBlock)
        ]
    if isinstance(message, UserMessage) and isinstance(message.content, list):
        return [
            ToolResult(id=b.tool_use_id, output=_flatten(b.content), is_error=bool(b.is_error))
            for b in message.content
            if isinstance(b, ToolResultBlock)
        ]
    if isinstance(message, ResultMessage):
        if message.is_error:
            detail = "; ".join(message.errors or []) or message.result or message.subtype
            return [AgentError(message=detail)]
        return [TurnComplete(cost_usd=message.total_cost_usd, usage=message.usage)]
    return []


def _sdk_tool(tool: Tool) -> SdkMcpTool[Any]:
    async def handler(arguments: dict[str, Any]) -> dict[str, Any]:
        result = await tool.invoke("", arguments)
        output = result.output
        text = output if isinstance(output, str) else json.dumps(output)
        return {"content": [{"type": "text", "text": text}], "is_error": result.is_error}

    return SdkMcpTool(
        name=tool.name,
        description=tool.description,
        input_schema=tool.json_schema(),
        handler=handler,
    )


def build_options(config: AgentConfig, workdir: Path, resume: str | None) -> ClaudeAgentOptions:
    web = list(WEB_TOOLS) if config.web_search else []
    return ClaudeAgentOptions(
        system_prompt=config.system_prompt,
        tools=web,
        allowed_tools=[MCP_PREFIX + t.name for t in config.tools] + web,
        mcp_servers={
            SERVER: create_sdk_mcp_server(SERVER, tools=[_sdk_tool(t) for t in config.tools])
        },
        strict_mcp_config=True,
        setting_sources=[],
        permission_mode="dontAsk",
        include_partial_messages=True,
        model=config.model,
        max_turns=config.max_turns,
        cwd=workdir,
        resume=resume,
    )


class ClaudeSession:
    def __init__(self, client: ClaudeSDKClient, resume: str | None) -> None:
        self._client = client
        self._session_id = resume

    @property
    def resume_token(self) -> str | None:
        return self._session_id

    async def send(self, text: str) -> AsyncIterator[AgentEvent]:
        await self._client.query(text)
        async for message in self._client.receive_response():
            if isinstance(message, ResultMessage):
                self._session_id = message.session_id
            for event in translate(message):
                yield event

    async def interrupt(self) -> None:
        await self._client.interrupt()

    async def close(self) -> None:
        await self._client.disconnect()


class ClaudeBackend:
    name = "claude"
    supports_web_search = True

    def __init__(self, workdir: Path | None = None) -> None:
        # Fixed, not per-session: Claude files a conversation under its working directory,
        # so resuming one needs the same directory.
        self._workdir = workdir or pupil_home() / "agent"

    async def open_session(self, config: AgentConfig, resume: str | None = None) -> ClaudeSession:
        check_capabilities(self, config)
        self._workdir.mkdir(parents=True, exist_ok=True)
        client = ClaudeSDKClient(build_options(config, self._workdir, resume))
        try:
            await client.connect()
        except Exception as exc:
            if _caused_by(exc, NotImplementedError):
                raise RuntimeError(
                    "this event loop cannot start subprocesses, which the Claude backend needs; "
                    "serve with `uvicorn --loop pupil_server.loop:loop_factory`"
                ) from exc
            raise
        return ClaudeSession(client, resume)


def _caused_by(exc: BaseException | None, kind: type[BaseException]) -> bool:
    while exc is not None:
        if isinstance(exc, kind):
            return True
        exc = exc.__cause__ or exc.__context__
    return False
