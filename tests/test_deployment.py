import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient
from watch_sieve import server


def test_health_database_failure_is_unavailable(monkeypatch):
    def unavailable():
        raise RuntimeError("private connection details")
    monkeypatch.setattr(server, "get_store", unavailable)
    response = TestClient(server.app).get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}


def test_health_works_with_store(monkeypatch):
    class HealthyStore:
        def query_topics(self, *, page, page_size):
            assert (page, page_size) == (1, 1)

    monkeypatch.setattr(server, "get_store", lambda: HealthyStore())
    assert TestClient(server.app).get("/api/health").json() == {"status": "ok"}


def test_container_database_override_preserves_credentials_and_options():
    path = Path(__file__).resolve().parents[1] / "scripts/docker-entrypoint.py"
    spec = importlib.util.spec_from_file_location("entrypoint", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    url = "postgresql://user:p%40ss@127.0.0.1:5432/watch_sieve?sslmode=prefer"
    assert module.database_url(url, "postgres16") == "postgresql://user:p%40ss@postgres16:5432/watch_sieve?sslmode=prefer"
    assert module.database_url(url, None) == url
