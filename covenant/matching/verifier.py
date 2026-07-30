from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Protocol

from jsonschema import Draft202012Validator

from covenant.registry.datahub import LookupResult
from src.obligations.candidate import sha256_text


SCHEMA_PATH = Path(__file__).parent / "schemas" / "match_result_v1.json"
CHECK_ORDER = {
    "schema_validation": 0,
    "tool_call_count": 1,
    "tool_input_consistency": 2,
    "identifier_verification": 3,
    "source_evidence_verification": 4,
    "tool_result_verification": 5,
    "identity_verification": 6,
    "timestamp_verification": 7,
}


class RegistryLookup(Protocol):
    def lookup(self, vendor_name: str, obligation_id: str) -> LookupResult: ...


def match_identity(result: Mapping[str, Any], document_text: str) -> str:
    return f"MATCH-{sha256_text(document_text)[:20]}"


def verify_match_result(
    result: Any,
    document_text: str,
    registry: RegistryLookup,
    *,
    observed_tool_call_count: int,
) -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text()))
    if not isinstance(result, Mapping):
        return _rejection("schema_validation", "match result is not an object")
    schema_errors = sorted(
        validator.iter_errors(result),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    for error in schema_errors:
        path = ".".join(str(item) for item in error.absolute_path) or "<root>"
        failures.append(
            _failure(
                "schema_validation",
                f"match result does not satisfy the schema at {path}",
            )
        )
    if observed_tool_call_count != 1:
        failures.append(
            _failure(
                "tool_call_count",
                "agreement lookup was not called exactly once",
            )
        )
    tool_call = result.get("tool_call")
    if isinstance(tool_call, Mapping):
        extracted_vendor = result.get("extracted_vendor_name")
        extracted_obligation = result.get("extracted_obligation_id")
        if (
            tool_call.get("vendor_name_sent") != extracted_vendor
            or tool_call.get("obligation_id_sent") != extracted_obligation
        ):
            failures.append(
                _failure(
                    "tool_input_consistency",
                    "lookup inputs do not match the extracted identifiers",
                )
            )
        if (
            not isinstance(extracted_vendor, str)
            or extracted_vendor not in document_text
            or not isinstance(extracted_obligation, str)
            or extracted_obligation not in document_text
        ):
            failures.append(
                _failure(
                    "identifier_verification",
                    "an extracted identifier is not a byte-for-byte source substring",
                )
            )
        for identifier_key, evidence_key in (
            ("extracted_vendor_name", "vendor_source_evidence"),
            ("extracted_obligation_id", "obligation_source_evidence"),
        ):
            identifier = result.get(identifier_key)
            evidence = result.get(evidence_key)
            if (
                not isinstance(identifier, str)
                or not isinstance(evidence, str)
                or identifier not in evidence
                or evidence not in document_text
            ):
                failures.append(
                    _failure(
                        "source_evidence_verification",
                        f"{evidence_key} is not verbatim evidence for its identifier",
                    )
                )
        sent_vendor = tool_call.get("vendor_name_sent")
        sent_obligation = tool_call.get("obligation_id_sent")
        if isinstance(sent_vendor, str) and isinstance(sent_obligation, str):
            try:
                authoritative = registry.lookup(sent_vendor, sent_obligation)
            except Exception:
                failures.append(
                    _failure(
                        "tool_result_verification",
                        "authoritative registry readback was unavailable",
                    )
                )
            else:
                if (
                    tool_call.get("tool_result_status") != authoritative.status
                    or tool_call.get("tool_result_match")
                    != authoritative.as_dict()["match"]
                ):
                    failures.append(
                        _failure(
                            "tool_result_verification",
                            "echoed lookup result does not match the authoritative registry",
                        )
                    )
    if result.get("match_id") != match_identity(result, document_text):
        failures.append(
            _failure(
                "identity_verification",
                "match identity does not bind the source and authoritative lookup",
            )
        )
    metadata = result.get("match_metadata")
    if isinstance(metadata, Mapping):
        try:
            started = datetime.fromisoformat(str(metadata["match_started_at"]))
            completed = datetime.fromisoformat(str(metadata["match_completed_at"]))
            if completed < started:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            failures.append(
                _failure(
                    "timestamp_verification",
                    "match timestamps are invalid or reversed",
                )
            )
    unique = {
        (item["check"], item["message"]): item
        for item in failures
    }
    ordered = sorted(
        unique.values(),
        key=lambda item: (CHECK_ORDER.get(item["check"], 99), item["message"]),
    )
    return {"status": "PASS"} if not ordered else {"status": "REJECT", "failures": ordered}


def rejected_match(result: Mapping[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(result))
    value["verification"] = verification
    return value


def _failure(check: str, message: str) -> dict[str, str]:
    return {"check": check, "message": message}


def _rejection(check: str, message: str) -> dict[str, Any]:
    return {"status": "REJECT", "failures": [_failure(check, message)]}
