from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from src.obligations.candidate import sha256_text, stable_json_hash

from .bedrock import BedrockCandidateExtractor, BedrockInvocationError, ModelExtraction


Clock = Callable[[], datetime]


@dataclass(frozen=True)
class ExtractionResult:
    status: str
    candidate: dict[str, Any] | None
    receipt: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_candidate(
    prior_text: str,
    candidate_text: str,
    *,
    prior_ref: str,
    candidate_ref: str,
    extractor: BedrockCandidateExtractor,
    now: Clock | None = None,
) -> ExtractionResult:
    clock = now or (lambda: datetime.now(timezone.utc))
    started_at = clock().astimezone(timezone.utc).isoformat()
    try:
        model = extractor.extract(prior_text, candidate_text)
    except BedrockInvocationError as exc:
        completed_at = clock().astimezone(timezone.utc).isoformat()
        return ExtractionResult(
            status="FAILED",
            candidate=None,
            receipt={
                "provider": "bedrock",
                "model_id": extractor.model_id,
                "status": "FAILED",
                "failure_category": exc.category,
                "safe_message": exc.safe_message,
                "attempts": exc.attempts,
                "extraction_started_at": started_at,
                "extraction_completed_at": completed_at,
            },
        )
    completed_at = clock().astimezone(timezone.utc).isoformat()
    if (
        model.payload["material_change"] is False
        and not model.payload["rules"]
        and not model.payload["unresolved_gaps"]
    ):
        return ExtractionResult(
            status="NO_MATERIAL_CHANGE",
            candidate=None,
            receipt={
                "provider": "bedrock",
                "model_id": model.model_id,
                "prompt_version": model.prompt_version,
                "schema_version": "covenant.candidate_delta.v1",
                "extraction_started_at": started_at,
                "extraction_completed_at": completed_at,
                "input_token_count": model.input_token_count,
                "output_token_count": model.output_token_count,
                "status": "NO_MATERIAL_CHANGE",
                "attempts": model.attempts,
            },
        )
    candidate = build_candidate(
        model,
        prior_text=prior_text,
        candidate_text=candidate_text,
        prior_ref=prior_ref,
        candidate_ref=candidate_ref,
        started_at=started_at,
        completed_at=completed_at,
    )
    return ExtractionResult(
        status="EXTRACTED_UNVERIFIED",
        candidate=candidate,
        receipt={
            **candidate["extraction_metadata"],
            "status": "EXTRACTED_UNVERIFIED",
            "attempts": model.attempts,
        },
    )


def build_candidate(
    model: ModelExtraction,
    *,
    prior_text: str,
    candidate_text: str,
    prior_ref: str,
    candidate_ref: str,
    started_at: str,
    completed_at: str,
) -> dict[str, Any]:
    payload = model.payload
    source_hash = sha256_text(candidate_text)
    rules = [
        {
            "rule_id": item["rule_id"],
            "usage_class": item["usage_class"],
            "effect": item["effect"],
            "evidence_status": item["evidence_status"],
            "confidence": item["confidence"],
            "citation": {
                "source_ref": candidate_ref,
                "source_sha256": source_hash,
                "quote": item["cited_clause_verbatim"],
            },
        }
        for item in payload["rules"]
    ]
    source_documents = [
        {
            "role": "superseded",
            "source_ref": prior_ref,
            "version": payload["supersedes_version"],
            "sha256": sha256_text(prior_text),
            "text_length": len(prior_text),
        },
        {
            "role": "candidate",
            "source_ref": candidate_ref,
            "version": payload["candidate_version"],
            "sha256": source_hash,
            "text_length": len(candidate_text),
        },
    ]
    identity = {
        "obligation_id": payload["obligation_id"],
        "supersedes_version": payload["supersedes_version"],
        "candidate_version": payload["candidate_version"],
        "effective_at": payload["effective_at"],
        "rules": sorted(
            [
                {
                    "usage_class": item["usage_class"],
                    "effect": item["effect"],
                    "evidence_status": item["evidence_status"],
                    "citation_sha256": sha256_text(item["citation"]["quote"]),
                }
                for item in rules
            ],
            key=lambda item: (item["usage_class"], item["effect"]),
        ),
        "source_document_hashes": [item["sha256"] for item in source_documents],
    }
    usage_classes = {
        "permitted": sorted(
            item["usage_class"] for item in rules if item["effect"] == "permitted"
        ),
        "prohibited": sorted(
            item["usage_class"] for item in rules if item["effect"] == "prohibited"
        ),
        "review_required": sorted(
            item["usage_class"]
            for item in rules
            if item["effect"] == "review_required"
        ),
    }
    extraction_metadata = {
        "provider": "bedrock",
        "model_id": model.model_id,
        "prompt_version": model.prompt_version,
        "schema_version": "covenant.candidate_delta.v1",
        "extraction_started_at": started_at,
        "extraction_completed_at": completed_at,
        "input_token_count": model.input_token_count,
        "output_token_count": model.output_token_count,
    }
    return {
        "schema_version": "covenant.candidate_delta.v1",
        "candidate_delta_id": f"DELTA-{stable_json_hash(identity)[:20]}",
        "obligation_id": payload["obligation_id"],
        "supersedes_version": payload["supersedes_version"],
        "candidate_version": payload["candidate_version"],
        "effective_at": payload["effective_at"],
        "rules": rules,
        "usage_classes": usage_classes,
        "material_change": payload["material_change"],
        "evidence_status": (
            "SUPPORTED"
            if not payload["unresolved_gaps"]
            and all(item["evidence_status"] == "SUPPORTED" for item in rules)
            else "GAPS_PRESENT"
        ),
        "unresolved_gaps": payload["unresolved_gaps"],
        "source_warnings": [],
        "source_documents": source_documents,
        "extractor": {
            "identity": "covenant.bedrock_candidate_extractor.v1",
            "extracted_at": completed_at,
        },
        "extraction_metadata": extraction_metadata,
        "lifecycle_state": "CANDIDATE",
    }
