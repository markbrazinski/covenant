from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.metadata.schema_classes import DatasetPropertiesClass

from src.datahub_client.core import emitter, graph
from src.datahub_client.mcp import call_mcp


PREFIX = "covenant.decision."


def desired_properties(decision: dict[str, Any], existing: dict[str, str]) -> dict[str, str]:
    recorded_at = existing.get(PREFIX + "recorded_at") or datetime.now(timezone.utc).isoformat()
    return {
        PREFIX + "id": decision["decision_id"],
        PREFIX + "obligation_id": "ATLAS-LIC-004",
        PREFIX + "disposition": decision["proposed_disposition"],
        PREFIX + "state": decision["decision_state"],
        PREFIX + "owner": decision["decision_owner"] or "",
        PREFIX + "evidence_reference": decision["evidence_reference"],
        PREFIX + "actor_class": decision["actor_class"],
        PREFIX + "recorded_at": recorded_at,
        PREFIX + "proposed_action": proposed_action(decision["proposed_disposition"]),
    }


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
        current = hub.get_aspect(decision["asset_urn"], DatasetPropertiesClass)
        if current is None:
            raise RuntimeError(f"cannot write decision to missing DataHub entity: {decision['asset_urn']}")
        updated = deepcopy(current)
        updated.customProperties = dict(current.customProperties or {})
        updated.customProperties.update(desired_properties(decision, updated.customProperties))
        out.emit(
            MetadataChangeProposalWrapper(
                entityType="dataset", entityUrn=decision["asset_urn"], aspect=updated
            )
        )
        written += 1
    return {"mode": "write", "proposed": len(decisions), "written": written, "verified": False}


def synthetic_override(decision: dict[str, Any], rationale: str) -> dict[str, str]:
    urn = decision["asset_urn"]
    hub = graph()
    current = hub.get_aspect(urn, DatasetPropertiesClass)
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
            PREFIX + "approval_actor": "synthetic_gate0_reviewer",
            PREFIX + "approval_rationale": rationale,
        }
    )
    emitter().emit(MetadataChangeProposalWrapper(entityType="dataset", entityUrn=urn, aspect=updated))
    return {"asset_urn": urn, "prior_state": prior, "new_state": "synthetic_test_approved", "label": "SYNTHETIC TEST APPROVAL", "actor": "synthetic_gate0_reviewer", "rationale": rationale}


def readback(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    raw = call_mcp([("get_entities", {"urns": [item["asset_urn"] for item in decisions]})])[0]
    entities = raw["result"]
    states: list[dict[str, str]] = []
    for entity in entities:
        props = {
            item["key"]: item.get("value", "")
            for item in entity.get("properties", {}).get("customProperties", [])
        }
        states.append({"asset_urn": entity["urn"], **{key: value for key, value in props.items() if key.startswith(PREFIX)}})
    expected = {item["asset_urn"]: item["decision_id"] for item in decisions}
    verified = len(states) == len(decisions) and all(
        state.get(PREFIX + "id") == expected[state["asset_urn"]] for state in states
    )
    return {"verified": verified, "count": len(states), "states": states, "read_interface": "DataHub MCP get_entities"}
