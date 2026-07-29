from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.metadata.schema_classes import (
    GlobalTagsClass,
    TagAssociationClass,
)

from src.datahub_client.core import (
    emitter,
    graph,
    native_custom_properties,
    property_contract,
    tag_urn,
)
from src.datahub_client.mcp import call_mcp


PREFIX = "covenant.decision."
DISPOSITION_TAG_PREFIX = "urn:li:tag:CovenantDisposition_"
STATE_TAG_PREFIX = "urn:li:tag:CovenantDecisionState_"


def decision_tags(disposition: str, state: str) -> set[str]:
    return {
        tag_urn(f"CovenantDisposition_{disposition}"),
        tag_urn(f"CovenantDecisionState_{state}"),
    }


def entity_tag_urns(entity: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    for association in entity.get("tags", {}).get("tags", []):
        tag = association.get("tag", {})
        urn = tag.get("urn") if isinstance(tag, dict) else tag
        if urn:
            found.add(urn)
    return found


def emit_decision_tags(urn: str, entity_type: str, disposition: str, state: str) -> None:
    current = graph().get_aspect(urn, GlobalTagsClass)
    retained = {
        association.tag
        for association in (current.tags if current else [])
        if not association.tag.startswith((DISPOSITION_TAG_PREFIX, STATE_TAG_PREFIX))
    }
    retained.update(decision_tags(disposition, state))
    emitter().emit(
        MetadataChangeProposalWrapper(
            entityType=entity_type,
            entityUrn=urn,
            aspect=GlobalTagsClass(
                tags=[TagAssociationClass(tag=value) for value in sorted(retained)]
            ),
        )
    )


def desired_properties(decision: dict[str, Any], existing: dict[str, str]) -> dict[str, str]:
    recorded_at = existing.get(PREFIX + "recorded_at") or datetime.now(timezone.utc).isoformat()
    properties = {
        PREFIX + "id": decision["decision_id"],
        PREFIX + "obligation_id": decision["obligation_id"],
        PREFIX + "disposition": decision["proposed_disposition"],
        PREFIX + "state": decision["decision_state"],
        PREFIX + "owner": decision["decision_owner"] or "",
        PREFIX + "evidence_reference": decision["evidence_reference"],
        PREFIX + "actor_class": decision["actor_class"],
        PREFIX + "recorded_at": recorded_at,
        PREFIX + "proposed_action": proposed_action(decision["proposed_disposition"]),
    }
    context = decision.get("gate2_context")
    if context:
        properties.update(
            {
                PREFIX + "candidate_delta_id": context["candidate_delta_id"],
                PREFIX + "activation_id": context["activation_id"],
                PREFIX + "candidate_version": str(context["candidate_version"]),
                PREFIX + "source_document_refs": json.dumps(
                    context["source_document_refs"], separators=(",", ":")
                ),
                PREFIX + "source_document_hashes": json.dumps(
                    context["source_document_hashes"],
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                PREFIX + "citations_sha256": context["citations_sha256"],
            }
        )
    return properties


def proposed_action(disposition: str) -> str:
    return {
        "allowed": "retain use and preserve evidence receipt",
        "remediate": "owner decision: clean rebuild, retrain, or deprecate",
        "stop_proposed": "human-authorized stop of synthetic redistribution workflow",
        "human_review": "governance review of preexisting anonymized derivative",
    }[disposition]


def apply(decisions: list[dict[str, Any]], *, read_only: bool = False, fail_after: int | None = None) -> dict[str, Any]:
    if read_only:
        return {"mode": "read_only", "proposed": len(decisions), "written": 0, "verified": False}
    out = emitter()
    hub = graph()
    written = 0
    for index, decision in enumerate(decisions):
        if fail_after is not None and index >= fail_after:
            raise RuntimeError("injected partial-write interruption")
        aspect_type, entity_type = property_contract(decision["asset_urn"])
        current = hub.get_aspect(decision["asset_urn"], aspect_type)
        if current is None:
            raise RuntimeError(f"cannot write decision to missing DataHub entity: {decision['asset_urn']}")
        updated = deepcopy(current)
        updated.customProperties = dict(current.customProperties or {})
        updated.customProperties.update(desired_properties(decision, updated.customProperties))
        out.emit(
            MetadataChangeProposalWrapper(
                entityType=entity_type, entityUrn=decision["asset_urn"], aspect=updated
            )
        )
        emit_decision_tags(
            decision["asset_urn"],
            entity_type,
            decision["proposed_disposition"],
            decision["decision_state"],
        )
        written += 1
    return {"mode": "write", "proposed": len(decisions), "written": written, "verified": False}


def synthetic_override(decision: dict[str, Any], rationale: str) -> dict[str, str]:
    urn = decision["asset_urn"]
    hub = graph()
    aspect_type, entity_type = property_contract(urn)
    current = hub.get_aspect(urn, aspect_type)
    if current is None:
        raise RuntimeError(f"cannot transition missing DataHub entity: {urn}")
    updated = deepcopy(current)
    updated.customProperties = dict(current.customProperties or {})
    prior = updated.customProperties.get(PREFIX + "state", decision["decision_state"])
    updated.customProperties.update(
        {
            PREFIX + "state": "synthetic_test_approved",
            PREFIX + "prior_state": prior,
            PREFIX + "approval_label": "SYNTHETIC TEST APPROVAL",
            PREFIX + "approval_actor": "synthetic_gate1a_reviewer",
            PREFIX + "approval_rationale": rationale,
        }
    )
    emitter().emit(
        MetadataChangeProposalWrapper(
            entityType=entity_type, entityUrn=urn, aspect=updated
        )
    )
    emit_decision_tags(
        urn,
        entity_type,
        decision["proposed_disposition"],
        "synthetic_test_approved",
    )
    return {
        "asset_urn": urn,
        "prior_state": prior,
        "new_state": "synthetic_test_approved",
        "label": "SYNTHETIC TEST APPROVAL",
        "actor": "synthetic_gate1a_reviewer",
        "rationale": rationale,
    }


def readback(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    raw = call_mcp([("get_entities", {"urns": [item["asset_urn"] for item in decisions]})])[0]
    entities = raw["result"]
    states: list[dict[str, Any]] = []
    expected = {item["asset_urn"]: item for item in decisions}
    seen: set[str] = set()
    unexpected_urns: list[str] = []
    for entity in entities:
        urn = entity["urn"]
        if urn not in expected:
            unexpected_urns.append(urn)
            continue
        if urn in seen:
            continue
        seen.add(urn)
        decision = expected[urn]
        tags = entity_tag_urns(entity)
        props = native_custom_properties(urn)
        expected_tags = decision_tags(
            decision["proposed_disposition"], props.get(PREFIX + "state", "")
        )
        states.append(
            {
                "asset_urn": urn,
                "entity_type": property_contract(urn)[1],
                "mcp_tags_verified": expected_tags.issubset(tags),
                "sdk_receipt_verified": props.get(PREFIX + "id")
                == decision["decision_id"],
                **{
                    key: value
                    for key, value in props.items()
                    if key.startswith(PREFIX)
                },
            }
        )
    expected_urns = set(expected)
    verified = seen == expected_urns and not unexpected_urns and all(
        state["mcp_tags_verified"] and state["sdk_receipt_verified"]
        for state in states
    )
    return {
        "verified": verified,
        "count": len(states),
        "states": states,
        "identity_set_verified": seen == expected_urns and not unexpected_urns,
        "unexpected_urns": sorted(set(unexpected_urns)),
        "read_interfaces": {
            "native_state": "DataHub MCP get_entities tags",
            "detailed_receipt": "DataHub SDK native property-aspect read",
        },
    }
