from pathlib import Path

from app.analyzer import analyze_repository
from app.repository import normalize_repo_url, project_id_for_url


def test_normalize_repo_url() -> None:
    assert normalize_repo_url("https://github.com/tiangolo/fastapi.git") == "https://github.com/tiangolo/fastapi"
    assert project_id_for_url("https://github.com/tiangolo/fastapi")


def test_analyze_repository_without_llm(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    (tmp_path / "README.md").write_text("# Demo\n\nA tiny FastAPI service for tests.", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n", encoding="utf-8")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
    )

    events = []
    report = analyze_repository(tmp_path, "https://github.com/example/demo", lambda m, p, payload=None: events.append((m, p)))

    assert report["stats"]["file_count"] == 3
    assert any(item["name"] == "FastAPI" for item in report["tech_stack"])
    assert events[-1][1] == 100
