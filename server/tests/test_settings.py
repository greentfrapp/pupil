from pathlib import Path

from pupil_server.settings import Settings


def test_a_db_path_under_home_can_start_with_a_tilde(monkeypatch):
    monkeypatch.setenv("PUPIL_DB_PATH", "~/Dropbox/pupil.db")
    assert Settings(_env_file=None).db_path == Path.home() / "Dropbox" / "pupil.db"
