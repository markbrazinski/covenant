#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from datahub.metadata.schema_classes import DatasetPropertiesClass, GlossaryTermInfoClass

from src.datahub_client.core import dataset_urn, emitter, graph, obligation_urn
from src.reconciler.writeback import PREFIX

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "allowed": 1,
    "human_review": 1,
    "remediate": 2,
    "stop_proposed": 1,
    "unaffected": 1,
}


def verify() -> dict[str, object]:
    emitter().test_connection()
    impact = json.loads((ROOT / "smoke-test" / "actual_impact_report.json").read_text())
    writeback = json.loads((ROOT / "smoke-test" / "writeback_readback.json").read_text())
    hub = graph()
    control_props = hub.get_aspect(dataset_urn("unrelated_control"), DatasetPropertiesClass).customProperties
    term_v4 = hub.get_aspect(obligation_urn("ATLAS-LIC-004"), GlossaryTermInfoClass, version=0)
    term_v3 = hub.get_aspect(obligation_urn("ATLAS-LIC-004"), GlossaryTermInfoClass, version=1)
    checks = {
        "datahub_connection": True,
        "exact_counts": impact["counts"] == EXPECTED,
        "five_confirmed_paths": len(impact["decisions"]) == 5 and all(item["lineage_paths"] for item in impact["decisions"]),
        "writeback_readback": writeback["verified"] is True,
        "unaffected_unmutated": not any(key.startswith(PREFIX) for key in control_props),
        "synthetic_approval_labeled": writeback.get("synthetic_override", {}).get("label") == "SYNTHETIC TEST APPROVAL",
        "license_versions": term_v4 is not None and term_v3 is not None and term_v4.customProperties.get("covenant.obligation_version") == "4" and term_v3.customProperties.get("covenant.obligation_version") == "3",
    }
    return {"passed": all(checks.values()), "checks": checks}


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)
