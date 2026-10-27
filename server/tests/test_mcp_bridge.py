from contextlib import asynccontextmanager

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import BaseModel

from pupil_server.agents import tool
from pupil_server.agents.mcp_bridge import McpBridge


class AddArgs(BaseModel):
    a: int
    b: int


@tool("add", "Add two integers.")
async def add(args: AddArgs) -> dict:
    return {"sum": args.a + args.b}


class Nothing(BaseModel):
    pass


@tool("ping", "Answer pong.")
async def ping(_: Nothing) -> str:
    return "pong"


@pytest.fixture
async def bridge():
    bridge = McpBridge()
    yield bridge
    await bridge.close()


@asynccontextmanager
async def connect(url: str):
    async with (
        streamable_http_client(url) as (read, write, *_),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        yield session


async def test_serves_a_sessions_tools_and_runs_them(bridge: McpBridge):
    url = await bridge.register([add])
    async with connect(url) as session:
        listed = await session.list_tools()
        assert [(t.name, t.description) for t in listed.tools] == [("add", "Add two integers.")]
        assert listed.tools[0].input_schema["required"] == ["a", "b"]

        result = await session.call_tool("add", {"a": 2, "b": 3})
        assert not result.is_error
        assert result.content[0].text == '{"sum": 5}'


async def test_a_failed_call_comes_back_as_an_error(bridge: McpBridge):
    url = await bridge.register([add])
    async with connect(url) as session:
        invalid = await session.call_tool("add", {"a": "two"})
        assert invalid.is_error and "invalid arguments" in invalid.content[0].text
        unknown = await session.call_tool("ping", {})
        assert unknown.is_error and unknown.content[0].text == "unknown tool 'ping'"


async def test_sessions_see_only_their_own_tools(bridge: McpBridge):
    first = await bridge.register([add])
    second = await bridge.register([ping])
    async with connect(first) as session:
        assert [t.name for t in (await session.list_tools()).tools] == ["add"]
    async with connect(second) as session:
        assert [t.name for t in (await session.list_tools()).tools] == ["ping"]


async def test_an_unknown_or_unregistered_url_is_refused(bridge: McpBridge):
    url = await bridge.register([add])
    bridge.unregister(url)
    async with httpx.AsyncClient() as http:
        assert (await http.post(url, json={})).status_code == 404
        assert (await http.post(url.rsplit("/", 1)[0] + "/nope", json={})).status_code == 404
