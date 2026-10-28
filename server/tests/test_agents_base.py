import pytest
from pydantic import BaseModel

from pupil_server.agents import (
    AgentConfig,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnComplete,
    UnsupportedCapability,
    tool,
)
from pupil_server.agents.fake import Call, FakeBackend, Say


class AddArgs(BaseModel):
    a: int
    b: int


@tool("add", "Add two integers.")
async def add(args: AddArgs) -> str:
    return str(args.a + args.b)


class Nothing(BaseModel):
    pass


@tool("explode", "Always fails.")
async def explode(_: Nothing) -> str:
    raise RuntimeError("boom")


def test_tool_decorator_builds_schema():
    assert add.name == "add"
    assert add.json_schema()["required"] == ["a", "b"]


def test_tool_decorator_rejects_non_model_handler():
    with pytest.raises(TypeError):

        @tool("bad", "No model.")
        async def bad(x: int) -> str:
            return str(x)


async def test_invoke_reports_validation_and_handler_errors():
    ok = await add.invoke("c1", {"a": 2, "b": 3})
    assert ok == ToolResult(id="c1", output="5")

    invalid = await add.invoke("c2", {"a": "two"})
    assert invalid.is_error and "invalid arguments" in str(invalid.output)

    failed = await explode.invoke("c3", {})
    assert failed.is_error and failed.output == "RuntimeError: boom"


def test_a_tool_result_reads_back_as_text_or_json():
    assert ToolResult(id="c1", output="5").text() == "5"
    assert ToolResult(id="c2", output={"lesson_id": "les_1"}).text() == '{"lesson_id": "les_1"}'


async def test_fake_backend_runs_tools_in_order():
    backend = FakeBackend([[Say("Adding now"), Call("add", {"a": 1, "b": 2}), Say("Done")]])
    session = await backend.open_session(AgentConfig(system_prompt="t", tools=[add]))

    events = [e async for e in session.send("1+2?")]

    kinds = [e.type for e in events]
    assert kinds[0] == "text_delta"
    call = next(e for e in events if isinstance(e, ToolCall))
    result = next(e for e in events if isinstance(e, ToolResult))
    assert (call.name, result.id, result.output) == ("add", call.id, "3")
    assert kinds.index("tool_call") < kinds.index("tool_result")
    assert isinstance(events[-1], TurnComplete)
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert text.split() == ["Adding", "now", "Done"]


async def test_fake_backend_unknown_tool_is_an_error_result():
    backend = FakeBackend([[Call("missing")]])
    session = await backend.open_session(AgentConfig(system_prompt="t"))
    results = [e async for e in session.send("go") if isinstance(e, ToolResult)]
    assert len(results) == 1 and results[0].is_error


async def test_web_search_requires_backend_support():
    backend = FakeBackend()
    backend.supports_web_search = False
    with pytest.raises(UnsupportedCapability):
        await backend.open_session(AgentConfig(system_prompt="t", web_search=True))
