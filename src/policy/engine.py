from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def load_policy(path: Path | None = None) -> dict[str, Any]:
    path = path or ROOT / "fixtures" / "expected_policy_delta.json"
    return json.loads(path.read_text())


def stable_decision_id(obligation_id: str, active_version: int, asset_urn: str) -> str:
    digest = hashlib.sha256(f"{obligation_id}|{active_version}|{asset_urn}".encode()).hexdigest()[:16]
    return f"COV-{obligation_id}-v{active_version}-{digest}"


def evaluate(asset_urn: str, metadata: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    usage = metadata.get("usage_class")
    rule = policy["rules"].get(usage, policy["default"])
    owner = metadata.get("owner")
    gaps: list[str] = []
    if not usage:
        gaps.append("missing_usage_class")
    if not owner:
        gaps.append("missing_owner")
    return {
        "asset_urn": asset_urn,
        "obligation_id": policy["obligation_id"],
        "usage_class": usage,
        "controlling_policy_rule": rule["rule"],
        "proposed_disposition": rule["disposition"],
        "decision_state": rule["decision_state"],
        "decision_owner": owner,
        "ownership_gap": owner is None,
        "evidence_gaps": gaps,
        "decision_id": stable_decision_id(policy["obligation_id"], policy["active_version"], asset_urn),
        "actor_class": "agent_system_recommendation",
        "confidence_meaning": "deterministic metadata rule matched" if usage in policy["rules"] else "insufficient metadata; routed to review",
    }
