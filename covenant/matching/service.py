from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from covenant.registry.datahub import DataHubAgreementRegistry

from .bedrock import BedrockAgreementMatcher, BedrockMatchError, ModelMatch
from .verifier import match_identity, verify_match_result


Clock = Callable[[], datetime]
EventSink = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True)
class MatchExecution:
    status: str
    result: dict[str, Any] | None
    verification: dict[str, Any] | None
    receipt: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def execute_match(
    document_text: str,
    *,
    matcher: BedrockAgreementMatcher,
    registry: DataHubAgreementRegistry,
    now: Clock | None = None,
    on_event: EventSink | None = None,
) -> MatchExecution:
    clock = now or (lambda: datetime.now(timezone.utc))
    started_at = clock().astimezone(timezone.utc).isoformat()
    if on_event:
        on_event("IDENTIFYING_VENDOR", {})

    def tool_called(value: dict[str, str]) -> None:
        if on_event:
            on_event(
                "TOOL_CALLED",
                {
                    "vendor_name_sent": value["vendor_name"],
                    "obligation_id_sent": value["obligation_id"],
                },
            )

    def tool_returned(value: Any) -> None:
        if on_event:
            on_event("TOOL_RETURNED", {"status": value.status})

    try:
        model = matcher.match(
            document_text,
            lookup=registry.lookup,
            on_tool_called=tool_called,
            on_tool_returned=tool_returned,
        )
    except BedrockMatchError as exc:
        completed_at = clock().astimezone(timezone.utc).isoformat()
        return MatchExecution(
            status="FAILED",
            result=None,
            verification=None,
            receipt={
                "provider": "bedrock",
                "model_id": matcher.model_id,
                "status": "FAILED",
                "failure_category": exc.category,
                "safe_message": exc.safe_message,
                "attempts": exc.attempts,
                "match_started_at": started_at,
                "match_completed_at": completed_at,
            },
        )
    completed_at = clock().astimezone(timezone.utc).isoformat()
    result = build_match_result(
        model,
        document_text=document_text,
        started_at=started_at,
        completed_at=completed_at,
    )
    if on_event:
        on_event("MATCH_VERIFYING", {})
    verification = verify_match_result(
        result,
        document_text,
        registry,
        observed_tool_call_count=model.tool_call_count,
    )
    receipt = {
        **result["match_metadata"],
        "status": verification["status"],
        "attempts": model.attempts,
    }
    if verification["status"] != "PASS":
        return MatchExecution(
            status="REJECTED",
            result=result,
            verification=verification,
            receipt=receipt,
        )
    status = (
        "MATCH_NOT_FOUND"
        if result["tool_call"]["tool_result_status"] == "NOT_FOUND"
        else "MATCH_VERIFIED"
    )
    return MatchExecution(
        status=status,
        result=result,
        verification=verification,
        receipt=receipt,
    )


def build_match_result(
    model: ModelMatch,
    *,
    document_text: str,
    started_at: str,
    completed_at: str,
) -> dict[str, Any]:
    payload = model.payload
    try:
        echoed_match = json.loads(payload["tool_result_match_json"])
    except (KeyError, TypeError, json.JSONDecodeError):
        echoed_match = {"invalid_model_echo": True}
    result = {
        "schema_version": "covenant.match_result.v1",
        "match_id": "MATCH-" + ("0" * 20),
        "extracted_vendor_name": payload["extracted_vendor_name"],
        "extracted_obligation_id": payload["extracted_obligation_id"],
        "vendor_source_evidence": payload["vendor_source_evidence"],
        "obligation_source_evidence": payload["obligation_source_evidence"],
        "tool_call": {
            "vendor_name_sent": model.tool_input["vendor_name"],
            "obligation_id_sent": model.tool_input["obligation_id"],
            "tool_result_status": payload["tool_result_status"],
            "tool_result_match": echoed_match,
            "tool_latency_ms": model.tool_result.lookup_latency_ms,
        },
        "match_metadata": {
            "provider": "bedrock",
            "model_id": model.model_id,
            "prompt_version": model.prompt_version,
            "match_started_at": started_at,
            "match_completed_at": completed_at,
            "input_token_count": model.input_token_count,
            "output_token_count": model.output_token_count,
        },
    }
    result["match_id"] = match_identity(result, document_text)
    return result
