from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.schemas import (
    ActivationRequest,
    AnalyzeRequest,
    ChangeSummary,
    ErrorProjection,
    RunDetail,
)
from src.api.service import APIStateError, CovenantService, DEFAULT_STATE_PATH
from src.api.store import RunStore
from src.datahub_client.core import emitter


def create_app(
    *,
    state_path: Path | None = DEFAULT_STATE_PATH,
    service: CovenantService | None = None,
) -> FastAPI:
    service = service or CovenantService(RunStore(state_path))
    service.ensure_canonical_change()
    app = FastAPI(
        title="Covenant API",
        version="0.4.0",
        description="Evidence-bound obligation change to DataHub operational response.",
    )
    app.state.covenant = service

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

    @app.get("/api/runs/{run_id}/events")
    def events(run_id: str) -> dict[str, Any]:
        value = service._run(run_id)
        return {"run_id": run_id, "events": value["events"], "error": value.get("error")}

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


app = create_app()
