"""Runtime configuration."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def pupil_home() -> Path:
    return Path.home() / "Pupil"


def _default_db_path() -> Path:
    """Where the database lives by default."""
    return pupil_home() / "pupil.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PUPIL_", env_file=".env")

    # Where `pnpm start` serves. `pnpm dev` uses 8787 regardless, as the client's proxy expects.
    host: str = "127.0.0.1"
    port: int = 8787

    log_level: str = "INFO"

    # Syllabi, lessons, attempts and learner progress.
    db_path: Path = Field(default_factory=_default_db_path)

    # Which agent runtime does the runs; "fake" needs no model or credentials.
    agent_backend: Literal["claude", "codex", "fake"] = "claude"
    # The model for its runs; None takes Pupil's default for the backend (sonnet for Claude).
    model: str | None = None
    # How hard the model thinks: the levels both Claude and Codex take.
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"


settings = Settings()
