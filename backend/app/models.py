from typing import Any, Literal

from pydantic import BaseModel, Field


AnalysisStatus = Literal["pending", "running", "completed", "failed"]


class AnalyzeRequest(BaseModel):
    repo_url: str = Field(..., description="Public GitHub repository URL")
    force: bool = False
    model: str | None = Field(default=None, description="Optional DeepSeek model name")


class AnalyzeResponse(BaseModel):
    project_id: str
    status: AnalysisStatus
    cached: bool = False


class ProgressEvent(BaseModel):
    type: str
    message: str
    percent: int = 0
    payload: dict[str, Any] | None = None


class ProjectSummary(BaseModel):
    id: str
    repo_url: str
    repo_name: str
    status: AnalysisStatus
    created_at: str
    updated_at: str


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    model: str | None = Field(default=None, description="Optional DeepSeek model name")


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
