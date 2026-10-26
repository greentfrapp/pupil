from pathlib import Path

from fastapi.testclient import TestClient

from pupil_server.agents.fake import FakeBackend
from pupil_server.app import create_app
from pupil_server.settings import Settings


def app_with(tmp_path: Path, client_dir: Path | None):
    return create_app(
        Settings(), db_path=tmp_path / "t.db", agent_backend=FakeBackend(), client_dir=client_dir
    )


def test_serves_the_built_client_beside_the_api(tmp_path: Path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<p>Pupil</p>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    with TestClient(app_with(tmp_path, dist)) as client:
        assert client.get("/").text == "<p>Pupil</p>"
        assert client.get("/assets/app.js").text == "console.log(1)"
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.get("/api/topics").status_code == 200


def test_serves_only_the_api_without_a_client(tmp_path: Path):
    with TestClient(app_with(tmp_path, None)) as client:
        assert client.get("/").status_code == 404
