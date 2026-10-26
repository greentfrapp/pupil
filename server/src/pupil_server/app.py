"""FastAPI application factory.

Wiring only: the database is opened once at startup, and the agent's runs are stopped before it
closes, so no run is still using it.

Routes live in `pupil_server.api`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from pupil_server import __version__
from pupil_server.agents import AgentBackend, make_backend
from pupil_server.api import lessons, topics
from pupil_server.db import Database, DatabaseTooNew
from pupil_server.lock import DatabaseInUse, DatabaseLock
from pupil_server.loop import LoopCannotSpawn, require_subprocess_support
from pupil_server.runs.service import Runs
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
    client_dir: Path | None = None,
) -> FastAPI:
    """The app; with `client_dir`, it also serves the built client from there."""
    config = settings or default_settings
    _configure_logging(config.log_level)
    backend = agent_backend or make_backend(config.agent_backend)

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
            app.state.runs = runs = Runs(db, backend)
            try:
                yield
            finally:
                await runs.close()
                await db.close()
        finally:
            lock.release()

    app = FastAPI(title="Pupil", version=__version__, lifespan=lifespan)
    app.state.settings = config

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(lessons.router)
    app.include_router(topics.router)
    if client_dir is not None:
        # Last, so the API's routes come first.
        app.mount("/", StaticFiles(directory=client_dir, html=True), name="client")
    return app


app = create_app()
