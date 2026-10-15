from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_env_example_copied_as_is_uses_defaults(tmp_path, monkeypatch):
    """`cp .env.example .env` (every value blank) must not break startup."""
    from pathlib import Path

    from app.config import Settings

    example = Path(__file__).resolve().parent.parent / ".env.example"
    (tmp_path / ".env").write_text(example.read_text())
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.session_max_age_days == 30
    assert s.cookie_secure is False
    assert s.extraction_provider == "groq"
