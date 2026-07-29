from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from datahub.metadata.schema_classes import GlobalTagsClass

from src.datahub_client.core import entity_urn, graph, native_custom_properties
from src.obligations.candidate import (
    SYNTHETIC_APPROVAL_LABEL,
    activate_synthetic_test,
    active_candidate_policy,
    extract_candidate,
    stable_json_hash,
    submit_for_review,
    validate_candidate,
)
from src.reconciler.writeback import PREFIX, apply, readback
from src.workflow.impact import analyse, write_results


def decision_context(candidate: dict[str, Any]) -> dict[str, Any]:
    source_hashes = {
        item["source_ref"]: item["sha256"] for item in candidate["source_documents"]
    }
    citations = [
        rule["citation"] for rule in sorted(candidate["rules"], key=lambda item: item["usage_class"])
    ]
    return {
        "candidate_delta_id": candidate["candidate_delta_id"],
        "activation_id": candidate["activation"]["activation_id"],
        "candidate_version": candidate["candidate_version"],
        "source_document_refs": sorted(source_hashes),
        "source_document_hashes": source_hashes,
        "citations_sha256": stable_json_hash(citations),
    }


def reconcile(
    candidate: dict[str, Any],
    decisions: list[dict[str, Any]],
    receipt_readback: dict[str, Any],
) -> dict[str, Any]:
    context = decision_context(candidate)
    expected = {item["asset_urn"]: item for item in decisions}
    checks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for state in receipt_readback["states"]:
        urn = state["asset_urn"]
        decision = expected.get(urn)
        if decision is None or urn in seen:
            continue
        seen.add(urn)
        checks.append(
            {
                "asset_urn": urn,
                "stable_decision_id": state.get(PREFIX + "id")
                == decision["decision_id"],
                "candidate_delta_id": state.get(PREFIX + "candidate_delta_id")
                == context["candidate_delta_id"],
                "activation_id": state.get(PREFIX + "activation_id")
                == context["activation_id"],
                "candidate_version": state.get(PREFIX + "candidate_version")
                == str(context["candidate_version"]),
                "citations_sha256": state.get(PREFIX + "citations_sha256")
                == context["citations_sha256"],
                "source_document_hashes": state.get(
                    PREFIX + "source_document_hashes"
                )
                == json.dumps(
                    context["source_document_hashes"],
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "confirmed_path": bool(decision.get("lineage_paths")),
                "mcp_tags_verified": state["mcp_tags_verified"],
                "sdk_receipt_verified": state["sdk_receipt_verified"],
            }
        )
    control_urn = entity_urn("unrelated_control")
    control_props = native_custom_properties(control_urn)
    control_tags = graph().get_aspect(control_urn, GlobalTagsClass)
    control_isolated = not control_props and not (control_tags.tags if control_tags else [])
    verified = (
        seen == set(expected)
        and len(checks) == len(decisions) == 5
        and receipt_readback.get("identity_set_verified", True)
        and all(all(value for key, value in check.items() if key != "asset_urn") for check in checks)
        and control_isolated
    )
    return {
        "verified": verified,
        "terminal_count": len(checks),
        "checks": checks,
        "unrelated_control_isolated": control_isolated,
    }


def rejected_candidate(
    candidate: dict[str, Any], validation: dict[str, Any], reason: str
) -> dict[str, Any]:
    rejected = deepcopy(candidate)
    rejected["lifecycle_state"] = "REJECTED"
    rejected["rejection"] = {
        "prior_state": candidate["lifecycle_state"],
        "new_state": "REJECTED",
        "actor_class": "deterministic_validator",
        "reason": reason,
        "validation_errors": validation["errors"],
    }
    return rejected


def run_change_to_action(
    old_path: Path,
    new_path: Path,
    *,
    synthetic_approve: bool,
) -> dict[str, Any]:
    candidate, documents = extract_candidate(old_path, new_path)
    validation = validate_candidate(candidate, documents, current_active_version=3)
    artifact: dict[str, Any] = {
        "claim": "Covenant turns a reviewed source-data obligation change into a graph-derived operational response plan.",
        "candidate": candidate,
        "validation": validation,
        "transitions": [],
        "impact": None,
        "writeback": None,
        "reconciliation": None,
    }
    if not validation["valid"]:
        artifact["candidate"] = rejected_candidate(
            candidate, validation, "deterministic evidence validation failed"
        )
        artifact["result"] = "ABSTAINED"
        return artifact
    if not candidate["material_change"]:
        artifact["candidate"] = rejected_candidate(
            candidate, validation, "no material obligation change"
        )
        artifact["result"] = "NO_MATERIAL_CHANGE"
        return artifact

    awaiting, review_event = submit_for_review(candidate, validation)
    artifact["candidate"] = awaiting
    artifact["transitions"].append(review_event)
    artifact["result"] = "AWAITING_REVIEW"
    if not synthetic_approve:
        return artifact

    active, activation_event = activate_synthetic_test(
        awaiting,
        label=SYNTHETIC_APPROVAL_LABEL,
        actor="synthetic_gate2_reviewer",
        rationale="Gate 2 end-to-end software test only; no real legal or governance approval.",
    )
    artifact["candidate"] = active
    artifact["transitions"].append(activation_event)
    policy = active_candidate_policy(active)
    report = analyse(policy)
    context = decision_context(active)
    for decision in report["decisions"]:
        decision["gate2_context"] = context
    write_results(report)
    write_result = apply(report["decisions"])
    receipt_readback = readback(report["decisions"])
    write_result["readback"] = receipt_readback
    write_result["verified"] = receipt_readback["verified"]
    reconciliation = reconcile(active, report["decisions"], receipt_readback)
    artifact.update(
        result="ACTIVE_RESPONSE_RECORDED",
        active_policy=policy,
        impact=report,
        writeback=write_result,
        reconciliation=reconciliation,
    )
    return artifact
