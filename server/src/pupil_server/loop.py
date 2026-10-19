"""Event loop for uvicorn: `--loop pupil_server.loop:loop_factory`.

The Claude backend runs the Claude Code CLI as a subprocess, which Windows only supports on
the Proactor loop. uvicorn picks the Selector loop whenever it serves from a child process
(as `--reload` does), so it has to be told.
"""

from __future__ import annotations

import asyncio
import sys


def loop_factory() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()
    return asyncio.new_event_loop()
