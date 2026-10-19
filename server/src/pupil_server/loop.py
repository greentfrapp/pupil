"""Event loop for uvicorn: `--loop pupil_server.loop:loop_factory`.

Agent backends may drive a CLI (Claude Code, Codex) as a subprocess, which Windows only
supports on the Proactor loop. uvicorn picks the Selector loop whenever it serves from a
child process (as `--reload` does), so it has to be told.
"""

from __future__ import annotations

import asyncio
import sys


class LoopCannotSpawn(RuntimeError):
    """The running event loop cannot start subprocesses."""


def loop_factory() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()
    return asyncio.new_event_loop()


def require_subprocess_support() -> None:
    """Fail fast at startup rather than when the first agent session opens."""
    loop = asyncio.get_running_loop()
    if sys.platform == "win32" and not isinstance(loop, asyncio.ProactorEventLoop):
        raise LoopCannotSpawn(
            f"{type(loop).__name__} cannot start subprocesses on Windows, which agent "
            "backends need; serve with `uvicorn --loop pupil_server.loop:loop_factory`"
        )
