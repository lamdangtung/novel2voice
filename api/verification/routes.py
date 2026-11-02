"""Mounted only with --verification; no arbitrary path or production provider access."""
import json
import re

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from api.verification import WorkspaceManager, WorkspaceError, self_check


class CreateWorkspace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,31}$")


class ResetWorkspace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: str = Field(max_length=64)


class SelfCheckOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fail_provider: Literal["none", "tts", "translator"] = "none"
    fail_on_call: int | None = Field(default=None, ge=1, le=3)
    fail_chapter: str = Field(default="", max_length=32)
    delay_ms: int = Field(default=0, ge=0, le=1000)


class SampleAudio(BaseModel):
    file: str
    chapter_id: str
    valid: bool
    duration_seconds: float | None


class SelfCheckReport(BaseModel):
    workspace: str
    run_id: str
    mode: Literal["verification"]
    status: Literal["passed", "failed"]
    fixture_version: str
    source_sha256: str
    tts_calls: int
    translator_calls: int
    outputs: list[SampleAudio]
    translation: str | None
    calls: list[dict]
    errors: list[dict]
    fault_plan: dict
    notice: str


class WorkspaceDetails(BaseModel):
    name: str
    path: str
    mode: Literal["verification"]
    manifest: dict
    latest_report: SelfCheckReport | None


class WorkspaceList(BaseModel):
    mode: Literal["verification"]
    root: str
    workspaces: list[WorkspaceDetails]


def create_router(manager=None):
    manager = manager or WorkspaceManager()
    router = APIRouter(prefix="/api/v1/verification", tags=["Verification — offline only"])

    @router.get("/workspaces", response_model=WorkspaceList)
    def list_workspaces():
        return {"mode": "verification", "workspaces": manager.list(), "root": str(manager.root)}

    @router.post("/workspaces", status_code=201, response_model=WorkspaceDetails)
    def create_workspace(body: CreateWorkspace):
        return manager.create(body.name)

    @router.post("/workspaces/{name}/reset", response_model=WorkspaceDetails)
    def reset_workspace(name: str, body: ResetWorkspace):
        return manager.reset(name, body.confirmation)

    @router.post("/workspaces/{name}/self-check", response_model=SelfCheckReport)
    def run_self_check(name: str, body: SelfCheckOptions):
        return self_check(manager, name, **body.model_dump())

    @router.get("/workspaces/{name}/runs/{run_id}/report")
    def download_report(name: str, run_id: str):
        with manager.lock(name) as path:
            manager.validate(path)
            if not re.fullmatch(r"run-\d{4,}", run_id):
                raise WorkspaceError("Run không hợp lệ.")
            report = path / "runs" / run_id / "report.json"
            if not report.is_file():
                raise WorkspaceError("Chưa có báo cáo cho run này.", "REPORT_NOT_FOUND", 404)
            return FileResponse(report, media_type="application/json", filename=f"{name}-{run_id}.json")

    @router.get("/workspaces/{name}/runs/{run_id}/audio/{filename}")
    def stream_sample(name: str, run_id: str, filename: str):
        with manager.lock(name) as path:
            manager.validate(path)
            if not re.fullmatch(r"run-\d{4,}", run_id) or not re.fullmatch(r"[A-Za-z0-9-]+\.mp3", filename):
                raise WorkspaceError("Audio kiểm thử không hợp lệ.")
            run = path / "runs" / run_id
            if not (run / "report.json").is_file():
                raise WorkspaceError("Chưa có kết quả audio.", "AUDIO_NOT_FOUND", 404)
            report = json.loads((run / "report.json").read_text(encoding="utf-8"))
            if filename not in {item["file"] for item in report["outputs"] if item["valid"]}:
                raise WorkspaceError("Không có audio này trong báo cáo.", "AUDIO_NOT_FOUND", 404)
            return FileResponse(run / filename, media_type="audio/mpeg")

    return router
