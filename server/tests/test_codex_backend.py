from pathlib import Path

from pupil_server.agents import AgentError, TextDelta, ToolCall, ToolResult, TurnComplete
from pupil_server.agents.codex import launch_overrides, run_turn, translate

# Notifications as `codex app-server` sends them, trimmed to the fields that matter.
USAGE = {"total": {"inputTokens": 9652, "outputTokens": 38}, "last": {}}


def tool_item(status: str, text: str | None = None, server: str = "pupil") -> dict:
    result = None if text is None else {"content": [{"type": "text", "text": text}]}
    item = {
        "type": "mcpToolCall",
        "id": "exec-1",
        "server": server,
        "tool": "get_lesson",
        "arguments": {"lesson_id": "les_1"},
        "status": status,
        "result": result,
        "error": None,
    }
    return {"item": item}


def completed(status: str, error: str | None = None) -> dict:
    return {"turn": {"status": status, "error": None if error is None else {"message": error}}}


def test_text_streams_from_deltas_only():
    assert translate("item/agentMessage/delta", {"delta": "Done"}) == [TextDelta(text="Done")]
    message = {"item": {"type": "agentMessage", "id": "msg_1", "text": "Done"}}
    assert translate("item/completed", message) == []


def test_an_app_tool_call_and_its_result():
    assert translate("item/started", tool_item("inProgress")) == [
        ToolCall(id="exec-1", name="get_lesson", input={"lesson_id": "les_1"})
    ]
    assert translate("item/completed", tool_item("completed", '{"id": "les_1"}')) == [
        ToolResult(id="exec-1", output='{"id": "les_1"}')
    ]


def test_a_failed_tool_call_is_an_error_result():
    failed = translate("item/completed", tool_item("failed", "NotFound: no lesson 'les_1'"))
    assert failed == [ToolResult(id="exec-1", output="NotFound: no lesson 'les_1'", is_error=True)]


def test_other_servers_tools_are_not_reported():
    assert translate("item/started", tool_item("inProgress", server="other")) == []


def test_the_turn_ends_with_its_usage_or_its_error():
    assert translate("turn/completed", completed("completed"), USAGE["total"]) == [
        TurnComplete(cost_usd=None, usage=USAGE["total"])
    ]
    assert translate("turn/completed", completed("failed", "usage limit reached")) == [
        AgentError(message="usage limit reached")
    ]
    assert translate("turn/completed", completed("interrupted")) == [
        AgentError(message="the turn was interrupted")
    ]


async def collect(notifications: list[tuple[str, dict]], max_turns: int | None, model=None):
    interrupts: list[bool] = []

    async def stream():
        for n in notifications:
            yield n

    async def interrupt():
        interrupts.append(True)

    events = [e async for e in run_turn(stream(), interrupt, max_turns, model)]
    return events, interrupts


async def test_a_turn_ends_with_its_model_and_latest_usage():
    events, interrupts = await collect(
        [
            ("thread/tokenUsage/updated", {"tokenUsage": USAGE}),
            ("item/started", tool_item("inProgress")),
            ("item/completed", tool_item("completed", "ok")),
            ("turn/completed", completed("completed")),
        ],
        max_turns=4,
        model="gpt-test",
    )
    assert [e.type for e in events] == ["tool_call", "tool_result", "turn_complete"]
    assert events[-1].usage == USAGE["total"]
    assert events[-1].model == "gpt-test"
    assert interrupts == []


async def test_a_turn_past_its_tool_call_limit_is_interrupted():
    call = [
        ("item/started", tool_item("inProgress")),
        ("item/completed", tool_item("completed", "ok")),
    ]
    events, interrupts = await collect(
        [*call, *call, ("turn/completed", completed("interrupted"))], max_turns=1
    )
    assert [e.type for e in events] == ["tool_call", "tool_result", "error"]
    assert events[-1] == AgentError(message="went past the limit of tool calls (1)")
    assert interrupts == [True]


def test_a_run_gets_the_apps_tools_and_none_of_the_users_setup(tmp_path: Path):
    (tmp_path / "config.toml").write_text(
        '[mcp_servers.node_repl]\ncommand = "node"\n\n[mcp_servers.github]\nurl = "https://x"\n'
    )
    overrides = launch_overrides("http://127.0.0.1:5000/mcp/tok", False, tmp_path)
    assert "features.shell_tool=false" in overrides
    assert "features.plugins=false" in overrides
    assert "notify=[]" in overrides
    assert "mcp_servers.node_repl.enabled=false" in overrides
    assert "mcp_servers.github.enabled=false" in overrides
    assert 'mcp_servers.pupil.url="http://127.0.0.1:5000/mcp/tok"' in overrides
    assert 'mcp_servers.pupil.default_tools_approval_mode="approve"' in overrides
    assert 'web_search="disabled"' in overrides


def test_web_search_is_on_only_when_asked(tmp_path: Path):
    assert 'web_search="live"' in launch_overrides("http://x", True, tmp_path)
