"""Runtime configuration."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_WORKSPACE_NAME = "Default"


def pupil_home() -> Path:
    return Path.home() / "Pupil"


def _default_db_path() -> Path:
    """Where the database lives by default."""
    return pupil_home() / "pupil.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PUPIL_", env_file=".env")

    mode: Literal["local", "remote"] = "local"
    host: str = "127.0.0.1"
    port: int = 8787

    log_level: str = "INFO"

    # Syllabi, lessons, attempts and learner progress.
    db_path: Path = Field(default_factory=_default_db_path)

    # Which agent runtime serves chat sessions; "fake" needs no model or credentials.
    agent_backend: Literal["claude", "fake"] = "claude"


settings = Settings()
