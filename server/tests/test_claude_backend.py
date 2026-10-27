from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from pydantic import BaseModel

from pupil_server.agents import AgentConfig, AgentError, TextDelta, ToolCall, ToolResult, tool
from pupil_server.agents.claude import build_options, translate


class EchoArgs(BaseModel):
    text: str


@tool("echo", "Echo text back.")
async def echo(args: EchoArgs) -> str:
    return args.text


def _result(**overrides) -> ResultMessage:
    fields = {
        "subtype": "success",
        "duration_ms": 1,
        "duration_api_ms": 1,
        "is_error": False,
        "num_turns": 1,
        "session_id": "s1",
        "total_cost_usd": 0.01,
    }
    return ResultMessage(**(fields | overrides))


def test_text_comes_from_deltas_only():
    delta = StreamEvent(
        uuid="u",
        session_id="s1",
        event={"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hi"}},
    )
    assert translate(delta) == [TextDelta(text="Hi")]
    final = AssistantMessage(content=[TextBlock(text="Hi")], model="m")
    assert translate(final) == []


def test_tool_names_are_the_apps_own():
    msg = AssistantMessage(
        content=[
            ToolUseBlock(id="t1", name="mcp__pupil__echo", input={"text": "x"}),
            ToolUseBlock(id="t2", name="WebSearch", input={"query": "q"}),
        ],
        model="m",
    )
    assert [e.name for e in translate(msg) if isinstance(e, ToolCall)] == ["echo", "web_search"]


def test_tool_results_are_flattened():
    msg = UserMessage(
        content=[ToolResultBlock(tool_use_id="t1", content=[{"type": "text", "text": "x"}])]
    )
    assert translate(msg) == [ToolResult(id="t1", output="x", is_error=False)]


def test_result_maps_to_completion_or_error():
    (done,) = translate(_result())
    assert done.type == "turn_complete" and done.cost_usd == 0.01
    (err,) = translate(_result(is_error=True, subtype="error_max_turns"))
    assert err == AgentError(message="error_max_turns")


def test_options_take_the_model_and_effort_asked_for(tmp_path: Path):
    options = build_options(AgentConfig(system_prompt="p", model="opus", effort="high"), tmp_path)
    assert (options.model, options.effort) == ("opus", "high")


def test_options_isolate_the_agent(tmp_path: Path):
    plain = build_options(AgentConfig(system_prompt="p", tools=[echo]), tmp_path)
    assert plain.tools == []
    assert plain.allowed_tools == ["mcp__pupil__echo"]
    assert plain.setting_sources == [] and plain.strict_mcp_config
    assert plain.permission_mode == "dontAsk"
    assert plain.include_partial_messages  # translate() takes text only from stream deltas

    assert plain.model == "sonnet"  # Pupil's default, not the user's Claude Code setting

    web = build_options(AgentConfig(system_prompt="p", web_search=True), tmp_path)
    assert set(web.tools) == {"WebSearch", "WebFetch"}
    # Under dontAsk, a tool that is available but not allowed is always denied.
    assert {"WebSearch", "WebFetch"} <= set(web.allowed_tools)
