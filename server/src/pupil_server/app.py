"""FastAPI application factory.

Wiring only: the database and agent sessions are opened once at startup and closed in reverse
order, so no session is still using the database when it closes.

Routes live in `pupil_server.api`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from pupil_server import __version__
from pupil_server.agents import AgentBackend, make_backend
from pupil_server.agents.sessions import SessionStore
from pupil_server.api import chat
from pupil_server.db import Database, DatabaseTooNew
from pupil_server.lock import DatabaseInUse, DatabaseLock
from pupil_server.loop import LoopCannotSpawn, require_subprocess_support
from pupil_server.settings import Settings
from pupil_server.settings import settings as default_settings

log = logging.getLogger(__name__)


def _configure_logging(level: str) -> None:
    """Configure sidecar logging."""
    logging.basicConfig(level=level.upper(), format="%(levelname)-8s %(name)s: %(message)s")


def create_app(
    settings: Settings | None = None,
    db_path: Path | None = None,
    agent_backend: AgentBackend | None = None,
) -> FastAPI:
    config = settings or default_settings
    _configure_logging(config.log_level)
    agents = SessionStore(agent_backend or make_backend(config.agent_backend))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            require_subprocess_support()
        except LoopCannotSpawn as exc:
            log.error("%s", exc)
            raise
        database = db_path or config.db_path
        lock = DatabaseLock(database)
        try:
            lock.acquire()
        except DatabaseInUse as exc:
            log.error("%s", exc)
            raise
        try:
            try:
                db = await Database.open(database)
            except DatabaseTooNew as exc:
                log.error("%s", exc)
                raise
            app.state.db = db
            try:
                yield
            finally:
                await agents.close_all()
                await db.close()
        finally:
            lock.release()

    app = FastAPI(title="Pupil", version=__version__, lifespan=lifespan)
    app.state.settings = config
    app.state.agents = agents

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__, "mode": config.mode}

    app.include_router(chat.router)
    return app


app = create_app()
