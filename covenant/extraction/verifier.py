from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timezone
from typing import Any, Callable, Mapping

from jsonschema import Draft202012Validator

from src.obligations.candidate import (
    CANDIDATE_DELTA_SCHEMA,
    SUPPORTED_USAGES,
    sha256_text,
    stable_json_hash,
    submit_for_review,
)


SourceValue = str | Mapping[str, Any]
SourceDocuments = Mapping[str, SourceValue]

PROHIBITIVE_MARKERS = (
    "prohibited",
    "not permitted",
    "may not",
    "shall not",
    "forbidden",
    "restricted",
    "disallowed",
)
REVIEW_MARKERS = (
    "review",
    "approval required",
    "subject to",
    "pending",
    "must be evaluated",
)
CHECK_ORDER = {
    "schema_validation": 0,
    "source_integrity": 1,
    "citation_verification": 2,
    "date_verification": 3,
    "semantic_consistency": 4,
    "vocabulary_consistency": 5,
    "evidence_eligibility": 6,
    "version_consistency": 7,
    "identity_consistency": 8,
}
USAGE_MARKERS = {
    "anonymized_derivative": ("anonymized derivative",),
    "customer_redistribution": ("redistribution",),
    "internal_analytics": ("internal analytics", "internal business analytics"),
    "ml_training": ("machine-learning training", "machine learning training"),
}


def _executed_candidate_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "covenant.executed_candidate_delta.v1",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            *CANDIDATE_DELTA_SCHEMA["required"],
            "source_warnings",
            "extraction_metadata",
        ],
        "properties": {
            "schema_version": {"const": "covenant.candidate_delta.v1"},
            "candidate_delta_id": {
                "type": "string",
                "pattern": "^DELTA-[a-f0-9]{20}$",
            },
            "obligation_id": {"type": "string", "minLength": 1},
            "supersedes_version": {"type": "integer"},
            "candidate_version": {"type": "integer"},
            "effective_at": {"type": "string", "minLength": 1},
            "rules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "rule_id",
                        "usage_class",
                        "effect",
                        "evidence_status",
                        "confidence",
                        "citation",
                    ],
                    "properties": {
                        "rule_id": {"type": "string", "minLength": 1},
                        "usage_class": {
                            "enum": sorted(SUPPORTED_USAGES),
                        },
                        "effect": {
                            "enum": CANDIDATE_DELTA_SCHEMA["effect_enum"],
                        },
                        "evidence_status": {
                            "enum": ["SUPPORTED", "GAP"],
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                        },
                        "citation": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "source_ref",
                                "source_sha256",
                                "quote",
                            ],
                            "properties": {
                                "source_ref": {
                                    "type": "string",
                                    "minLength": 1,
                                },
                                "source_sha256": {
                                    "type": "string",
                                    "pattern": "^[a-f0-9]{64}$",
                                },
                                "quote": {
                                    "type": "string",
                                    "minLength": 1,
                                },
                            },
                        },
                    },
                },
            },
            "usage_classes": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "permitted",
                    "prohibited",
                    "review_required",
                ],
                "properties": {
                    effect: {
                        "type": "array",
                        "items": {"enum": sorted(SUPPORTED_USAGES)},
                        "uniqueItems": True,
                    }
                    for effect in CANDIDATE_DELTA_SCHEMA["effect_enum"]
                },
            },
            "material_change": {"type": "boolean"},
            "evidence_status": {"enum": ["SUPPORTED", "GAPS_PRESENT"]},
            "unresolved_gaps": {
                "type": "array",
                "items": {"type": "string"},
            },
            "source_warnings": {
                "type": "array",
                "items": {"type": "string"},
            },
            "source_documents": {
                "type": "array",
                "minItems": 2,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "role",
                        "source_ref",
                        "version",
                        "sha256",
                    ],
                    "properties": {
                        "role": {"enum": ["superseded", "candidate"]},
                        "source_ref": {"type": "string", "minLength": 1},
                        "version": {"type": "integer"},
                        "sha256": {
                            "type": "string",
                            "pattern": "^[a-f0-9]{64}$",
                        },
                        "text_length": {
                            "type": "integer",
                            "minimum": 0,
                        },
                    },
                },
            },
            "extractor": {
                "type": "object",
                "additionalProperties": False,
                "required": ["identity", "extracted_at"],
                "properties": {
                    "identity": {"type": "string", "minLength": 1},
                    "extracted_at": {"type": "string", "minLength": 1},
                },
            },
            "extraction_metadata": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "provider",
                    "model_id",
                    "prompt_version",
                    "schema_version",
                    "extraction_started_at",
                    "extraction_completed_at",
                    "input_token_count",
                    "output_token_count",
                ],
                "properties": {
                    "provider": {"const": "bedrock"},
                    "model_id": {"type": "string", "minLength": 1},
                    "prompt_version": {"type": "string", "minLength": 1},
                    "schema_version": {
                        "const": "covenant.candidate_delta.v1",
                    },
                    "extraction_started_at": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "extraction_completed_at": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "input_token_count": {
                        "type": "integer",
                        "minimum": 0,
                    },
                    "output_token_count": {
                        "type": "integer",
                        "minimum": 0,
                    },
                },
            },
            "lifecycle_state": {"const": "CANDIDATE"},
        },
    }


def _failure(
    check: str,
    message: str,
    *,
    rule_id: str | None = None,
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "check": check,
        "message": message,
    }


def _source_text(value: SourceValue | None) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        text = value.get("text")
        return text if isinstance(text, str) else None
    return None


def _source_created_at(value: SourceValue | None) -> str | None:
    if not isinstance(value, Mapping):
        return None
    created_at = value.get("created_at")
    return created_at if isinstance(created_at, str) else None


def _parse_iso(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed_date = date.fromisoformat(value)
        parsed = datetime.combine(parsed_date, time.min)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _expected_candidate_id(candidate: dict[str, Any]) -> str | None:
    rules = candidate.get("rules")
    sources = candidate.get("source_documents")
    if not isinstance(rules, list) or not isinstance(sources, list):
        return None
    try:
        identity = {
            "obligation_id": candidate["obligation_id"],
            "supersedes_version": candidate["supersedes_version"],
            "candidate_version": candidate["candidate_version"],
            "effective_at": candidate["effective_at"],
            "rules": sorted(
                [
                    {
                        "usage_class": item["usage_class"],
                        "effect": item["effect"],
                        "evidence_status": item["evidence_status"],
                        "citation_sha256": sha256_text(
                            item["citation"]["quote"]
                        ),
                    }
                    for item in rules
                ],
                key=lambda item: (item["usage_class"], item["effect"]),
            ),
            "source_document_hashes": [
                item["sha256"]
                for item in sources
            ],
        }
    except (KeyError, TypeError):
        return None
    return f"DELTA-{stable_json_hash(identity)[:20]}"


def verify_candidate_delta(
    candidate: Any,
    source_documents: Any,
) -> dict[str, Any]:
    """Deterministically verify a model candidate without mutating it."""
    if not isinstance(candidate, Mapping):
        return {
            "status": "REJECT",
            "failures": [
                _failure(
                    "schema_validation",
                    "candidate does not satisfy the schema at <root>",
                )
            ],
        }
    safe_source_documents = (
        source_documents
        if isinstance(source_documents, Mapping)
        else {}
    )
    failures: list[dict[str, Any]] = []

    validator = Draft202012Validator(_executed_candidate_schema())
    for error in sorted(
        validator.iter_errors(candidate),
        key=lambda item: tuple(str(part) for part in item.path),
    ):
        error_path = list(error.path)
        path = ".".join(str(item) for item in error_path) or "<root>"
        rule_id = None
        if (
            len(error_path) >= 2
            and error_path[0] == "rules"
            and isinstance(error_path[1], int)
        ):
            rule_index = error_path[1]
            candidate_rules = candidate.get("rules", [])
            if (
                isinstance(candidate_rules, list)
                and rule_index < len(candidate_rules)
                and isinstance(candidate_rules[rule_index], Mapping)
            ):
                candidate_rule_id = candidate_rules[rule_index].get("rule_id")
                if isinstance(candidate_rule_id, str):
                    rule_id = candidate_rule_id
        failures.append(
            _failure(
                "schema_validation",
                f"candidate does not satisfy the schema at {path}",
                rule_id=rule_id,
            )
        )

    candidate_sources = candidate.get("source_documents")
    safe_sources = candidate_sources if isinstance(candidate_sources, list) else []
    candidate_source_refs: set[str] = set()
    source_role_counts = {"superseded": 0, "candidate": 0}
    all_source_refs: list[str] = []
    for source in safe_sources:
        if not isinstance(source, Mapping):
            continue
        ref = source.get("source_ref")
        if not isinstance(ref, str):
            continue
        all_source_refs.append(ref)
        role = source.get("role")
        if role in source_role_counts:
            source_role_counts[role] += 1
        if role == "candidate":
            candidate_source_refs.add(ref)
            if source.get("version") != candidate.get("candidate_version"):
                failures.append(
                    _failure(
                        "source_integrity",
                        "candidate source version does not match the candidate",
                    )
                )
        elif role == "superseded" and source.get("version") != candidate.get(
            "supersedes_version"
        ):
            failures.append(
                _failure(
                    "source_integrity",
                    "superseded source version does not match the candidate",
                )
            )
        text = _source_text(safe_source_documents.get(ref))
        if text is None:
            failures.append(
                _failure(
                    "source_integrity",
                    "a referenced source document is unavailable",
                )
            )
            continue
        if sha256_text(text) != source.get("sha256"):
            failures.append(
                _failure(
                    "source_integrity",
                    "a referenced source document hash does not match",
                )
            )
        text_length = source.get("text_length")
        if text_length is not None and text_length != len(text):
            failures.append(
                _failure(
                    "source_integrity",
                    "a referenced source document length does not match",
                )
            )
    for role, count in source_role_counts.items():
        if count != 1:
            failures.append(
                _failure(
                    "source_integrity",
                    f"candidate must contain exactly one {role} source",
                )
            )
    if len(all_source_refs) != len(set(all_source_refs)):
        failures.append(
            _failure(
                "source_integrity",
                "source roles must reference distinct documents",
            )
        )

    candidate_rules = candidate.get("rules")
    safe_rules = candidate_rules if isinstance(candidate_rules, list) else []
    seen_rule_ids: set[str] = set()
    seen_effects: dict[str, set[str]] = {}
    for rule in safe_rules:
        if not isinstance(rule, Mapping):
            continue
        rule_id = rule.get("rule_id")
        safe_rule_id = rule_id if isinstance(rule_id, str) else None
        if safe_rule_id in seen_rule_ids:
            failures.append(
                _failure(
                    "schema_validation",
                    "rule identifiers must be unique",
                    rule_id=safe_rule_id,
                )
            )
        if safe_rule_id is not None:
            seen_rule_ids.add(safe_rule_id)

        usage = rule.get("usage_class")
        effect = rule.get("effect")
        if usage not in SUPPORTED_USAGES:
            failures.append(
                _failure(
                    "vocabulary_consistency",
                    "rule usage class is outside the executed vocabulary",
                    rule_id=safe_rule_id,
                )
            )
        if isinstance(usage, str) and isinstance(effect, str):
            seen_effects.setdefault(usage, set()).add(effect)
        if rule.get("evidence_status") != "SUPPORTED":
            failures.append(
                _failure(
                    "evidence_eligibility",
                    "rule evidence status is not supported",
                    rule_id=safe_rule_id,
                )
            )

        citation = rule.get("citation")
        if not isinstance(citation, Mapping):
            continue
        ref = citation.get("source_ref")
        quote = citation.get("quote")
        text = (
            _source_text(safe_source_documents.get(ref))
            if isinstance(ref, str)
            else None
        )
        if ref not in candidate_source_refs:
            failures.append(
                _failure(
                    "citation_verification",
                    "rule citation does not reference the candidate-version source",
                    rule_id=safe_rule_id,
                )
            )
        if (
            text is None
            or not isinstance(quote, str)
            or not quote
            or quote not in text
        ):
            failures.append(
                _failure(
                    "citation_verification",
                    "rule citation is not a byte-for-byte source substring",
                    rule_id=safe_rule_id,
                )
            )
        elif citation.get("source_sha256") != sha256_text(text):
            failures.append(
                _failure(
                    "citation_verification",
                    "rule citation source hash does not match",
                    rule_id=safe_rule_id,
                )
            )

        if not isinstance(quote, str):
            continue
        lowered = quote.lower()
        if usage in USAGE_MARKERS and not any(
            marker in lowered for marker in USAGE_MARKERS[usage]
        ):
            failures.append(
                _failure(
                    "semantic_consistency",
                    "rule citation does not support its usage class",
                    rule_id=safe_rule_id,
                )
            )
        if effect == "prohibited" and not any(
            marker in lowered for marker in PROHIBITIVE_MARKERS
        ):
            failures.append(
                _failure(
                    "semantic_consistency",
                    "prohibition rule lacks a prohibitive source marker",
                    rule_id=safe_rule_id,
                )
            )
        elif effect == "review_required" and not any(
            marker in lowered for marker in REVIEW_MARKERS
        ):
            failures.append(
                _failure(
                    "semantic_consistency",
                    "review rule lacks a review source marker",
                    rule_id=safe_rule_id,
                )
            )
        elif effect == "permitted" and any(
            marker in lowered for marker in PROHIBITIVE_MARKERS
        ):
            failures.append(
                _failure(
                    "semantic_consistency",
                    "allowance rule cites explicit prohibitive language",
                    rule_id=safe_rule_id,
                )
            )

    for usage, effects in seen_effects.items():
        if len(effects) > 1:
            failures.append(
                _failure(
                    "semantic_consistency",
                    "one usage class has contradictory effects",
                    rule_id=None,
                )
            )
    expected_usage_classes = {
        effect: sorted(
            usage
            for usage, effects in seen_effects.items()
            if effect in effects
        )
        for effect in CANDIDATE_DELTA_SCHEMA["effect_enum"]
    }
    if candidate.get("usage_classes") != expected_usage_classes:
        failures.append(
            _failure(
                "semantic_consistency",
                "usage-class summary does not match the verified rules",
            )
        )

    effective_at = candidate.get("effective_at")
    effective_datetime: datetime | None = None
    if not isinstance(effective_at, str):
        failures.append(
            _failure(
                "date_verification",
                "effective date is not valid ISO 8601",
            )
        )
    else:
        try:
            effective_datetime = _parse_iso(effective_at)
        except ValueError:
            failures.append(
                _failure(
                    "date_verification",
                    "effective date is not valid ISO 8601",
                )
            )
    for ref in candidate_source_refs:
        created_at = _source_created_at(safe_source_documents.get(ref))
        if created_at is None or effective_datetime is None:
            continue
        try:
            created_datetime = _parse_iso(created_at)
        except ValueError:
            failures.append(
                _failure(
                    "date_verification",
                    "candidate source creation date is not valid ISO 8601",
                )
            )
            continue
        if effective_datetime <= created_datetime:
            failures.append(
                _failure(
                    "date_verification",
                    "effective date must be after candidate source creation",
                )
            )

    if candidate.get("unresolved_gaps"):
        failures.append(
            _failure(
                "evidence_eligibility",
                "candidate contains unresolved evidence gaps",
            )
        )
    if candidate.get("evidence_status") != "SUPPORTED":
        failures.append(
            _failure(
                "evidence_eligibility",
                "candidate evidence status is not supported",
            )
        )
    if candidate.get("material_change") is not True:
        failures.append(
            _failure(
                "evidence_eligibility",
                "candidate does not contain a material change",
            )
        )
    elif not safe_rules:
        failures.append(
            _failure(
                "evidence_eligibility",
                "material change must contain at least one supported rule",
            )
        )

    expected_candidate_id = _expected_candidate_id(candidate)
    if (
        expected_candidate_id is not None
        and candidate.get("candidate_delta_id") != expected_candidate_id
    ):
        failures.append(
            _failure(
                "identity_consistency",
                "candidate identity does not match its evidence-bound content",
            )
        )

    timestamp_fields = [
        candidate.get("extractor", {}).get("extracted_at")
        if isinstance(candidate.get("extractor"), Mapping)
        else None,
    ]
    metadata = candidate.get("extraction_metadata")
    if isinstance(metadata, Mapping):
        timestamp_fields.extend(
            [
                metadata.get("extraction_started_at"),
                metadata.get("extraction_completed_at"),
            ]
        )
    parsed_timestamps: list[datetime] = []
    for value in timestamp_fields:
        if not isinstance(value, str):
            continue
        try:
            parsed_timestamps.append(_parse_iso(value))
        except ValueError:
            failures.append(
                _failure(
                    "date_verification",
                    "extraction timestamp is not valid ISO 8601",
                )
            )
    if len(parsed_timestamps) == 3:
        extracted_at, started_at, completed_at = parsed_timestamps
        if completed_at < started_at or extracted_at != completed_at:
            failures.append(
                _failure(
                    "date_verification",
                    "extraction timestamps are not chronologically consistent",
                )
            )

    unique_failures = list(
        {
            (
                item["rule_id"],
                item["check"],
                item["message"],
            ): item
            for item in failures
        }.values()
    )
    unique_failures.sort(
        key=lambda item: (
            CHECK_ORDER.get(item["check"], len(CHECK_ORDER)),
            item["rule_id"] or "",
            item["message"],
        )
    )
    return (
        {"status": "PASS"}
        if not unique_failures
        else {"status": "REJECT", "failures": unique_failures}
    )


def verify_and_submit_for_review(
    candidate: dict[str, Any],
    source_documents: SourceDocuments,
    *,
    current_active_version: int,
    now: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    """Transition only a verified model candidate into AWAITING_REVIEW."""
    verification = verify_candidate_delta(candidate, source_documents)
    candidate_version = candidate.get("candidate_version")
    if (
        verification["status"] == "PASS"
        and (
            not isinstance(candidate_version, int)
            or candidate_version <= current_active_version
        )
    ):
        verification = {
            "status": "REJECT",
            "failures": [
                _failure(
                    "version_consistency",
                    "candidate version must be newer than the active version",
                )
            ],
        }
    if verification["status"] != "PASS":
        rejected = deepcopy(candidate)
        rejected["lifecycle_state"] = "REJECTED"
        rejected["verification"] = verification
        return rejected, verification, None
    reviewed, event = submit_for_review(
        candidate,
        {"valid": True},
        now=now,
    )
    reviewed["verification"] = verification
    return reviewed, verification, event
