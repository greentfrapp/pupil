"""Runtime configuration."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_WORKSPACE_NAME = "Default"


def _pupil_home() -> Path:
    return Path.home() / "Pupil"


def _default_db_path() -> Path:
    """Where the event log lives by default."""
    return _pupil_home() / "pupil.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PUPIL_", env_file=".env")

    mode: Literal["local", "remote"] = "local"
    host: str = "127.0.0.1"
    port: int = 8787

    log_level: str = "INFO"

    # Event log + derived state tables.
    db_path: Path = Field(default_factory=_default_db_path)


settings = Settings()
