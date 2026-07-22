from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from src.datahub_client.core import (
    entity_urn,
    load_fixture,
    native_custom_properties,
    native_name,
    property_contract,
)
from src.datahub_client.mcp import call_mcp
from src.policy.engine import evaluate, load_policy

ROOT = Path(__file__).resolve().parents[2]


class ImpactUnavailableError(RuntimeError):
    """The live metadata dependency is unavailable; no impact set was produced."""


def live_mcp(calls: list[tuple[str, dict[str, Any]]]) -> list[Any]:
    try:
        return call_mcp(calls)
    except Exception as exc:
        raise ImpactUnavailableError(
            "live DataHub MCP unavailable; Covenant did not produce an affected set"
        ) from exc


def custom_properties(entity: dict[str, Any]) -> dict[str, str]:
    return {
        item["key"]: item.get("value", "")
        for item in entity.get("properties", {}).get("customProperties", [])
    }


def owner(entity: dict[str, Any]) -> str | None:
    owners = entity.get("ownership", {}).get("owners", [])
    return owners[0].get("owner", {}).get("urn") if owners else None


def entity_name(entity: dict[str, Any]) -> str:
    properties = entity.get("properties", {})
    return (
        entity.get("name")
        or properties.get("name")
        or properties.get("title")
        or entity["urn"]
    )


def paths_as_urns(path_result: dict[str, Any]) -> list[list[str]]:
    return [
        [node["urn"] for node in path.get("path", [])]
        for path in path_result.get("paths", [])
    ]


def validate_active_version(policy_version: int, source_version: int) -> None:
    if policy_version < source_version:
        raise RuntimeError("stale obligation version cannot replace active DataHub metadata")
    if policy_version != source_version:
        raise RuntimeError("policy and source active obligation versions differ")


def attach_paths(decision: dict[str, Any], path_result: dict[str, Any]) -> dict[str, Any]:
    decision = dict(decision)
    decision["lineage_paths"] = paths_as_urns(path_result)
    if not decision["lineage_paths"]:
        decision["evidence_gaps"] = [*decision.get("evidence_gaps", []), "missing_confirmed_lineage_path"]
    return decision


def analyse(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    fixture = load_fixture()
    policy = policy or load_policy()
    source_urn = entity_urn("vendor_demographics_raw", fixture)
    control_urn = entity_urn("unrelated_control", fixture)

    search, source_detail, lineage = live_mcp(
        [
            ("search", {"query": "vendor_demographics_raw", "num_results": 10}),
            ("get_entities", {"urns": source_urn}),
            ("get_lineage", {"urn": source_urn, "upstream": False, "max_hops": 6, "max_results": 50}),
        ]
    )
    matches = search.get("searchResults", [])
    exact = [item for item in matches if item.get("entity", {}).get("urn") == source_urn]
    if len(exact) != 1:
        raise RuntimeError(f"source resolution expected one exact validated match, found {len(exact)}")
    source_entity = source_detail["result"]
    source_props = custom_properties(source_entity)
    if source_props.get("covenant.obligation_id") != policy["obligation_id"]:
        raise RuntimeError("resolved source does not carry the controlling obligation")
    source_version = int(source_props.get("covenant.active_obligation_version", "0"))
    validate_active_version(policy["active_version"], source_version)

    # GMS writes are synchronous, while the lineage search index converges
    # asynchronously. Require two identical live-MCP snapshots before routing.
    stable_reads = 0
    previous_signature: tuple[str, ...] | None = None
    for _ in range(6):
        downstream = lineage.get("downstreams", {})
        signature = tuple(
            sorted(
                item.get("entity", {}).get("urn", "")
                for item in downstream.get("searchResults", [])
            )
        )
        if signature == previous_signature:
            stable_reads += 1
        else:
            stable_reads = 0
            previous_signature = signature
        if stable_reads >= 1:
            break
        time.sleep(1)
        lineage = live_mcp(
            [
                (
                    "get_lineage",
                    {
                        "urn": source_urn,
                        "upstream": False,
                        "max_hops": 6,
                        "max_results": 50,
                    },
                )
            ]
        )[0]
    else:
        raise RuntimeError("DataHub MCP downstream lineage did not converge")

    downstream = lineage.get("downstreams", {})
    downstream_results = downstream.get("searchResults", [])
    downstream_urns = {item["entity"]["urn"] for item in downstream_results}
    if control_urn in downstream_urns:
        raise RuntimeError("unrelated control was discovered in the affected graph")

    # MCP 0.6.0 intentionally returns different compact projections per native
    # entity type. The affected set is exclusively MCP lineage-derived; native
    # SDK aspect reads supply usage markers omitted from Dashboard and MLModel
    # projections.
    terminal_urns = sorted(
        urn
        for urn in downstream_urns
        if native_custom_properties(urn).get("covenant.terminal") == "true"
    )
    detail, control_detail = live_mcp(
        [
            ("get_entities", {"urns": terminal_urns}),
            ("get_entities", {"urns": control_urn}),
        ]
    )
    entities = {entity["urn"]: entity for entity in detail["result"]}
    path_results = live_mcp(
        [
            (
                "get_lineage_paths_between",
                {"source_urn": source_urn, "target_urn": urn, "direction": "downstream"},
            )
            for urn in terminal_urns
        ]
    )

    decisions: list[dict[str, Any]] = []
    for urn, path_result in zip(terminal_urns, path_results, strict=True):
        entity = entities[urn]
        props = native_custom_properties(urn)
        metadata = {
            "usage_class": props.get("covenant.usage_class") or None,
            "owner": owner(entity),
        }
        decision = evaluate(urn, metadata, policy)
        decision.update(
            asset_name=native_name(urn),
            entity_type=property_contract(urn)[1],
            metadata_interfaces={
                "usage_and_terminal": "DataHub SDK native property-aspect read",
                "ownership": "DataHub MCP get_entities",
                "lineage": "DataHub MCP get_lineage_paths_between",
            },
            evidence_reference="smoke-test/actual_impact_report.json",
        )
        decisions.append(attach_paths(decision, path_result))

    counts = Counter(item["proposed_disposition"] for item in decisions)
    counts["unaffected"] = 1
    control = control_detail["result"]
    return {
        "scenario": "SYNTHETIC Northstar Commerce / Atlas Signals",
        "source": {
            "urn": source_urn,
            "resolved_via": "DataHub MCP search plus exact URN and obligation metadata validation",
            "obligation_id": policy["obligation_id"],
            "active_version": policy["active_version"],
        },
        "graph": {
            "downstream_entity_count": downstream.get("total"),
            "terminal_count": len(terminal_urns),
            "read_interface": "mcp-server-datahub 0.6.0 live MCP",
        },
        "counts": dict(sorted(counts.items())),
        "decisions": decisions,
        "unaffected": [
            {
                "asset_urn": control_urn,
                "asset_name": entity_name(control),
                "reason": "absent from DataHub MCP downstream lineage result",
            }
        ],
    }


def write_results(report: dict[str, Any]) -> None:
    output = ROOT / "smoke-test" / "actual_impact_report.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    rows = "\n".join(
        f"| `{item['asset_name']}` | `{item['usage_class']}` | "
        f"`{item['proposed_disposition']}` | `{item['decision_state']}` | "
        f"{item['decision_owner'] or 'OWNERSHIP GAP'} | {len(item['lineage_paths'])} |"
        for item in report["decisions"]
    )
    text = f"""# Covenant Native Semantic Graph Results

**SYNTHETIC DEMONSTRATION DATA ONLY**

The governed source was resolved with live DataHub MCP search and validated against the controlling obligation metadata. DataHub MCP returned {report['graph']['downstream_entity_count']} downstream entities across native entity types and multiple hops. Lineage and ownership came from live MCP responses; terminal and usage fields came from live native property-aspect reads because MCP 0.6.0 omits those custom fields for Dashboard and MLModel projections.

| Terminal | Usage class | Proposed disposition | Decision state | Owner | Confirmed paths |
|---|---|---|---|---|---:|
{rows}

Counts: `{json.dumps(report['counts'], sort_keys=True)}`.

The unrelated control was read independently and was absent from the affected graph. It is not eligible for writeback. Models are proposed for clean rebuild, retraining, deprecation review, or owner decision; no machine-unlearning claim is made.
"""
    (ROOT / "smoke-test" / "results.md").write_text(text)
