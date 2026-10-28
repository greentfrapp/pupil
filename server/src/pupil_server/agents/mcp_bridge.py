"""Serve app tools to an agent that runs in another process, over MCP on a loopback port.

The Claude SDK serves tools from inside the app; other runtimes (Codex) only reach tools
through an MCP server. Each session registers its tools and gets a URL of its own, with a
random token in the path, so a run only ever sees its own topic's tools.
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
from collections.abc import Iterator
from typing import Any

import uvicorn
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from pupil_server.agents.base import Tool

PREFIX = "/mcp/"


class _Server(uvicorn.Server):
    """Leaves Ctrl+C to the app's own server, which stops the bridge as it shuts down."""

    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


class McpBridge:
    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Tool]] = {}
        self._server = Server("pupil", on_list_tools=self._list_tools, on_call_tool=self._call_tool)
        self._manager: StreamableHTTPSessionManager | None = None
        self._http: uvicorn.Server | None = None
        self._serving: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._port = 0

    async def register(self, tools: list[Tool]) -> str:
        """Serve these tools to one session; the URL to give its agent."""
        await self._start()
        token = secrets.token_urlsafe(16)
        self._sessions[token] = {t.name: t for t in tools}
        return f"http://127.0.0.1:{self._port}{PREFIX}{token}"

    def unregister(self, url: str) -> None:
        self._sessions.pop(url.rsplit("/", 1)[-1], None)

    async def close(self) -> None:
        if self._http is not None and self._serving is not None:
            self._http.should_exit = True
            await self._serving
        self._http = self._serving = self._manager = None

    async def _start(self) -> None:
        async with self._lock:
            if self._http is not None:
                return
            # Stateless: each request stands alone, so nothing is kept between a run's calls.
            self._manager = StreamableHTTPSessionManager(
                self._server, stateless=True, json_response=True
            )
            config = uvicorn.Config(
                self._app, host="127.0.0.1", port=0, interface="asgi3", log_level="warning"
            )
            self._http = http = _Server(config)
            self._serving = asyncio.create_task(self._serve(self._manager, http))
            while not http.started:
                if self._serving.done():
                    serving, self._http = self._serving, None
                    serving.result()  # raise why it couldn't start
                await asyncio.sleep(0.01)
            self._port = http.servers[0].sockets[0].getsockname()[1]

    @staticmethod
    async def _serve(manager: StreamableHTTPSessionManager, http: uvicorn.Server) -> None:
        # The manager's task group is entered and left here, in one task, as anyio requires.
        async with manager.run():
            await http.serve()

    async def _app(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            return
        path: str = scope["path"]
        if not path.startswith(PREFIX) or path.removeprefix(PREFIX) not in self._sessions:
            await send({"type": "http.response.start", "status": 404, "headers": []})
            await send({"type": "http.response.body", "body": b""})
            return
        assert self._manager is not None
        await self._manager.handle_request(scope, receive, send)

    def _tools(self, ctx: Any) -> dict[str, Tool]:
        """The tools of the session whose URL the request came to."""
        return self._sessions.get(ctx.request.url.path.removeprefix(PREFIX), {})

    async def _list_tools(self, ctx: Any, _: Any) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[
                types.Tool(name=t.name, description=t.description, input_schema=t.json_schema())
                for t in self._tools(ctx).values()
            ]
        )

    async def _call_tool(
        self, ctx: Any, params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        tool = self._tools(ctx).get(params.name)
        if tool is None:
            text, is_error = f"unknown tool {params.name!r}", True
        else:
            result = await tool.invoke("", params.arguments or {})
            text, is_error = result.text(), result.is_error
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=text)], is_error=is_error
        )
