#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.workflow.change_to_action import run_change_to_action

ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run Covenant's bounded synthetic obligation change-to-action slice."
    )
    parser.add_argument(
        "--old", type=Path, default=ROOT / "fixtures" / "atlas_license_v3.md"
    )
    parser.add_argument(
        "--new", type=Path, default=ROOT / "fixtures" / "atlas_license_v4.md"
    )
    parser.add_argument("--synthetic-approve", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "smoke-test" / "gate2-change-to-action.json",
    )
    args = parser.parse_args()
    artifact = run_change_to_action(
        args.old, args.new, synthetic_approve=args.synthetic_approve
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "result": artifact["result"],
                "candidate_delta_id": artifact["candidate"]["candidate_delta_id"],
                "lifecycle_state": artifact["candidate"]["lifecycle_state"],
                "validation_valid": artifact["validation"]["valid"],
                "impact_counts": (artifact["impact"] or {}).get("counts"),
                "reconciled": (artifact["reconciliation"] or {}).get("verified"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    raise SystemExit(
        0
        if artifact["result"]
        in {"AWAITING_REVIEW", "ACTIVE_RESPONSE_RECORDED", "NO_MATERIAL_CHANGE"}
        else 2
    )
