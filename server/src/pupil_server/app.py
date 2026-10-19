"""FastAPI application factory.

Wiring only: the Store and RunRegistry are created once at startup and shut down in
reverse order, because the registry's backends emit into the store and must be closed
before it is.

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
    async def _serving(app: FastAPI, database: Path) -> AsyncIterator[None]:
        # The registry isn't wired up yet; serve without it until it is.
        registry = getattr(app.state, "registry", None)
        if registry is None:
            yield
            return
        await registry.policy.preload()
        await registry.expire_orphaned_permissions()
        await registry.settle_stranded_runs()
        await registry.settle_stranded_jobs()
        registry.start()
        try:
            yield
        finally:
            await registry.close()

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
            async with _serving(app, database):
                try:
                    yield
                finally:
                    await agents.close_all()
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
