"""The Claude backend needs a loop that can start subprocesses (not billed: no turn is sent)."""

import asyncio
import sys

import pytest

from pupil_server.agents import AgentConfig
from pupil_server.agents.claude import ClaudeBackend
from pupil_server.loop import loop_factory

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="Selector loop limit is Windows-only"
)


async def _open_and_close(workdir) -> None:
    session = await ClaudeBackend(workdir=workdir).open_session(AgentConfig(system_prompt="t"))
    await session.close()


@windows_only
def test_selector_loop_gives_a_clear_error(tmp_path):
    with pytest.raises(RuntimeError, match="cannot start subprocesses"):
        asyncio.run(_open_and_close(tmp_path), loop_factory=asyncio.SelectorEventLoop)


def test_loop_factory_can_start_the_claude_cli(tmp_path):
    asyncio.run(_open_and_close(tmp_path), loop_factory=loop_factory)
