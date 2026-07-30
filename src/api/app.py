from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from src.api.matching import (
    EXTRACTION_TERMINAL_PHASES,
    TERMINAL_PHASES,
    MatchCoordinator,
    document_text_from_fixture,
    document_text_from_upload,
)
from src.api.schemas import (
    ActivationRequest,
    AnalyzeRequest,
    ChangeSummary,
    ErrorProjection,
    RunDetail,
    WritebackProgress,
)
from src.api.service import APIStateError, CovenantService, DEFAULT_STATE_PATH
from src.api.store import RunStore
from src.datahub_client.core import emitter

STATE_ROOT = (Path(__file__).resolve().parents[2] / "smoke-test" / "generated-state").resolve()


def configured_state_path(value: str) -> Path:
    candidate = Path(value)
    resolved = (candidate if candidate.is_absolute() else STATE_ROOT.parents[1] / candidate).resolve()
    if not resolved.is_relative_to(STATE_ROOT) or resolved == STATE_ROOT:
        raise RuntimeError(
            "COVENANT_STATE_PATH must resolve to a file under smoke-test/generated-state"
        )
    return resolved


def create_app(
    *,
    state_path: Path | None = DEFAULT_STATE_PATH,
    service: CovenantService | None = None,
    match_coordinator: MatchCoordinator | None = None,
) -> FastAPI:
    service = service or CovenantService(RunStore(state_path))
    service.ensure_canonical_change()
    matcher = match_coordinator or MatchCoordinator(service.store, service)
    app = FastAPI(
        title="Covenant API",
        version="0.4.0",
        description="Evidence-bound obligation change to DataHub operational response.",
    )
    app.state.covenant = service
    app.state.matches = matcher
    allowed_origins = [
        origin.strip()
        for origin in os.getenv(
            "COVENANT_CORS_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173",
        ).split(",")
        if origin.strip()
    ]
    if "*" in allowed_origins:
        raise RuntimeError("COVENANT_CORS_ORIGINS must not contain a wildcard origin")
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type"],
        )

    @app.exception_handler(APIStateError)
    async def state_error(_: Request, exc: APIStateError) -> JSONResponse:
        projection = ErrorProjection(
            code=exc.code,
            message=str(exc),
            affected_set_produced=exc.affected_set_produced,
            retryable=exc.retryable,
        )
        return JSONResponse(status_code=exc.status_code, content=projection.model_dump())

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        try:
            emitter().test_connection()
            datahub = "connected"
        except Exception:
            datahub = "unavailable"
        return {
            "service": "covenant",
            "status": "ok" if datahub == "connected" else "degraded",
            "datahub": datahub,
            "runtime": "official local DataHub Quickstart v1.6.0",
        }

    @app.get("/api/changes", response_model=list[ChangeSummary])
    def changes() -> list[dict[str, Any]]:
        return service.list_changes()

    @app.get("/agreements/registered")
    @app.get("/api/agreements/registered")
    def registered_agreements() -> list[dict[str, Any]]:
        return matcher.registered()

    @app.post("/analyses/match")
    @app.post("/api/analyses/match")
    async def start_match(
        document: UploadFile | None = File(default=None),
        fixture_path: str | None = Form(default=None),
    ) -> dict[str, str]:
        if (document is None) == (fixture_path is None):
            raise APIStateError(
                "ONE_DOCUMENT_REQUIRED",
                "provide exactly one uploaded agreement or canonical fixture reference",
                status_code=422,
            )
        if document is not None:
            filename = document.filename or "agreement"
            text = document_text_from_upload(filename, await document.read())
            document_ref = f"analysis-upload:{filename}"
        else:
            text, document_ref = document_text_from_fixture(fixture_path or "")
        return matcher.start(text, document_ref=document_ref)

    @app.get("/analyses/{match_id}")
    @app.get("/api/analyses/{match_id}")
    def match_detail(match_id: str) -> dict[str, Any]:
        return matcher.detail(match_id)

    @app.get("/analyses/{match_id}/events")
    @app.get("/api/analyses/{match_id}/events")
    async def match_events(match_id: str, request: Request) -> StreamingResponse:
        matcher.detail(match_id)

        async def stream():
            emitted = 0
            while True:
                value = matcher.detail(match_id)
                events = value["events"]
                for event in events[emitted:]:
                    yield (
                        f"id: {event['sequence']}\n"
                        f"event: {event['phase']}\n"
                        f"data: {json.dumps(event, sort_keys=True)}\n\n"
                    )
                    emitted += 1
                if value["phase"] in TERMINAL_PHASES:
                    return
                if await request.is_disconnected():
                    return
                await asyncio.sleep(0.1)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/analyses/{match_id}/extract")
    @app.post("/api/analyses/{match_id}/extract")
    def extract_matched_agreement(match_id: str) -> dict[str, Any]:
        return matcher.extract(match_id)

    @app.get("/analyses/{match_id}/extraction-events")
    @app.get("/api/analyses/{match_id}/extraction-events")
    async def extraction_events(
        match_id: str,
        request: Request,
    ) -> StreamingResponse:
        matcher.detail(match_id)

        async def stream():
            emitted = 0
            while True:
                value = matcher.detail(match_id)
                events = value.get("extraction_events", [])
                for event in events[emitted:]:
                    yield (
                        f"id: {event['sequence']}\n"
                        f"event: {event['phase']}\n"
                        f"data: {json.dumps(event, sort_keys=True)}\n\n"
                    )
                    emitted += 1
                if value.get("extraction_phase") in EXTRACTION_TERMINAL_PHASES:
                    return
                if await request.is_disconnected():
                    return
                await asyncio.sleep(0.1)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/api/changes/analyze", response_model=ChangeSummary)
    def analyze(request: AnalyzeRequest) -> dict[str, Any]:
        return service.change_summary(service.analyze_change(request))

    @app.get("/api/changes/{change_id}")
    def change(change_id: str) -> dict[str, Any]:
        record = service._change(change_id)
        return {
            "summary": service.change_summary(record),
            "candidate": record["candidate"],
            "validation": record["validation"],
            "transitions": record["transitions"],
            "documents": record["documents"],
        }

    @app.post("/api/changes/{change_id}/activate", response_model=RunDetail)
    def activate(change_id: str, request: ActivationRequest) -> dict[str, Any]:
        run = service.activate(change_id, **request.model_dump())
        return service.run_detail(run)

    @app.post("/api/changes/{change_id}/impact", response_model=RunDetail)
    def impact(change_id: str) -> dict[str, Any]:
        change = service._change(change_id)
        activation = change["candidate"].get("activation")
        if not activation:
            raise APIStateError(
                "ACTIVATION_REQUIRED",
                "impact analysis requires a separately activated reviewed candidate",
            )
        run_id = activation["activation_id"].replace("ACTIVATION-", "RUN-", 1)
        return service.run_detail(service.run_impact(run_id))

    @app.get("/api/runs/{run_id}", response_model=RunDetail)
    def run(run_id: str) -> dict[str, Any]:
        return service.run_detail(service._run(run_id))

    @app.get("/api/runs", response_model=list[RunDetail])
    def runs() -> list[dict[str, Any]]:
        return [
            service.run_detail(value)
            for value in service.store.snapshot()["runs"].values()
        ]

    @app.get("/api/runs/{run_id}/events")
    def events(run_id: str) -> dict[str, Any]:
        value = service._run(run_id)
        return {"run_id": run_id, "events": value["events"], "error": value.get("error")}

    @app.get(
        "/api/runs/{run_id}/writeback-progress",
        response_model=WritebackProgress,
    )
    def writeback_progress(run_id: str) -> dict[str, Any]:
        return service.writeback_progress(run_id)

    @app.post("/api/runs/{run_id}/writeback", response_model=RunDetail)
    def writeback(run_id: str) -> dict[str, Any]:
        return service.run_detail(service.writeback(run_id))

    @app.post("/api/runs/{run_id}/replay", response_model=RunDetail)
    def replay(run_id: str) -> dict[str, Any]:
        return service.run_detail(service.replay(run_id))

    @app.get("/api/decisions/{decision_id}")
    def decision(decision_id: str) -> dict[str, Any]:
        for run_value in service.store.snapshot()["runs"].values():
            detail = service.run_detail(run_value)
            for item in detail["decisions"]:
                if item["decision_id"] == decision_id:
                    return item
        raise APIStateError("DECISION_NOT_FOUND", "decision was not found", status_code=404)

    return app


configured_state = os.getenv("COVENANT_STATE_PATH", "").strip()
app = create_app(
    state_path=configured_state_path(configured_state) if configured_state else DEFAULT_STATE_PATH
)
