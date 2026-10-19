"""The server must run on an event loop that can start subprocesses."""

import asyncio
import sys
from pathlib import Path

import pytest

from pupil_server.agents.fake import FakeBackend
from pupil_server.app import create_app
from pupil_server.loop import LoopCannotSpawn, loop_factory
from pupil_server.settings import Settings


async def _run_subprocess() -> int:
    proc = await asyncio.create_subprocess_exec(sys.executable, "-c", "")
    return await proc.wait()


def test_loop_factory_can_run_subprocesses():
    assert asyncio.run(_run_subprocess(), loop_factory=loop_factory) == 0


@pytest.mark.skipif(sys.platform != "win32", reason="Selector loop limit is Windows-only")
def test_startup_refuses_a_loop_that_cannot_spawn(tmp_path: Path):
    app = create_app(Settings(), db_path=tmp_path / "t.db", agent_backend=FakeBackend())

    async def start() -> None:
        async with app.router.lifespan_context(app):
            pass

    with pytest.raises(LoopCannotSpawn, match="pupil_server.loop:loop_factory"):
        asyncio.run(start(), loop_factory=asyncio.SelectorEventLoop)
