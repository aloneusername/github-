import asyncio
import json
from typing import AsyncIterator

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.analyzer import analyze_repository
from app.chat import stream_answer
from app.db import clear_project_events, get_events_after, get_project, get_project_by_repo, init_db, list_projects, save_event, upsert_project
from app.deepseek import normalize_model
from app.models import AnalyzeRequest, AnalyzeResponse, ChatRequest, ProjectSummary
from app.repository import clone_or_update, local_path_for_repo, normalize_repo_url, project_id_for_url, repo_name_from_url


app = FastAPI(title="project-helper", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/projects", response_model=list[ProjectSummary])
def projects() -> list[dict]:
    return list_projects()


@app.get("/api/projects/{project_id}")
def project(project_id: str) -> dict:
    item = get_project(project_id)
    if not item:
        raise HTTPException(status_code=404, detail="Project not found")
    return item


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest, background_tasks: BackgroundTasks) -> AnalyzeResponse:
    try:
        repo_url = normalize_repo_url(str(request.repo_url))
        model_name = normalize_model(request.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = get_project_by_repo(repo_url)
    if existing and existing["status"] == "completed" and not request.force:
        return AnalyzeResponse(project_id=existing["id"], status="completed", cached=True)

    project_id = project_id_for_url(repo_url)
    record = {
        "id": project_id,
        "repo_url": repo_url,
        "repo_name": repo_name_from_url(repo_url),
        "local_path": str(local_path_for_repo(repo_url)),
        "status": "pending",
        "report": existing.get("report") if existing else None,
        "error": None,
    }
    upsert_project(record)
    clear_project_events(project_id)
    save_event(project_id, {"type": "queued", "message": "任务已加入队列", "percent": 1})
    background_tasks.add_task(run_analysis, project_id, repo_url, request.force, model_name)
    return AnalyzeResponse(project_id=project_id, status="pending", cached=False)


@app.get("/api/analyze/{project_id}/events")
async def analysis_events(project_id: str) -> StreamingResponse:
    if not get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return StreamingResponse(event_stream(project_id), media_type="text/event-stream")


@app.post("/api/projects/{project_id}/chat/stream")
async def chat(project_id: str, request: ChatRequest) -> StreamingResponse:
    item = get_project(project_id)
    if not item:
        raise HTTPException(status_code=404, detail="Project not found")
    if item["status"] != "completed":
        raise HTTPException(status_code=409, detail="Project analysis is not completed")
    try:
        model_name = normalize_model(request.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StreamingResponse(chat_stream(item, request.question, model_name), media_type="text/event-stream")


def run_analysis(project_id: str, repo_url: str, force: bool = False, model_name: str | None = None) -> None:
    project = get_project(project_id)
    if not project:
        return

    def emit(message: str, percent: int, payload: dict | None = None) -> None:
        save_event(project_id, {"type": "progress", "message": message, "percent": percent, "payload": payload})

    try:
        project["status"] = "running"
        upsert_project(project)
        emit("开始克隆或更新仓库", 5)
        repo_path = clone_or_update(repo_url, force=force)
        project["local_path"] = str(repo_path)
        upsert_project(project)
        report = analyze_repository(repo_path, repo_url, emit=emit, model_name=model_name)
        project["status"] = "completed"
        project["report"] = report
        project["error"] = None
        upsert_project(project)
        save_event(project_id, {"type": "completed", "message": "报告已生成", "percent": 100, "payload": {"report": report}})
    except Exception as exc:
        project["status"] = "failed"
        project["error"] = str(exc)
        upsert_project(project)
        save_event(project_id, {"type": "failed", "message": str(exc), "percent": 100})


async def event_stream(project_id: str) -> AsyncIterator[str]:
    last_id = 0
    while True:
        events = get_events_after(project_id, last_id)
        for event in events:
            last_id = event["id"]
            yield sse(event["type"], event)
            if event["type"] in {"completed", "failed"}:
                return
        await asyncio.sleep(0.5)


async def chat_stream(project: dict, question: str, model_name: str | None = None) -> AsyncIterator[str]:
    async for token in stream_answer(project, question, model_name=model_name):
        yield sse("token", {"content": token})
    yield sse("done", {"content": ""})


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
