#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.reconciler.writeback import apply, readback, synthetic_override

ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--synthetic-override", action="store_true")
    args = parser.parse_args()
    report = json.loads((ROOT / "smoke-test" / "actual_impact_report.json").read_text())
    result = apply(report["decisions"], read_only=args.read_only)
    if not args.read_only:
        result["readback"] = readback(report["decisions"])
        result["verified"] = result["readback"]["verified"]
    if args.synthetic_override:
        target = next(item for item in report["decisions"] if item["proposed_disposition"] == "human_review")
        result["synthetic_override"] = synthetic_override(
            target,
            "Gate 1A software transition test only; no real governance decision or external action.",
        )
        result["post_override_readback"] = readback(report["decisions"])
    (ROOT / "smoke-test" / "writeback_readback.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({"mode": result["mode"], "written": result["written"], "verified": result["verified"]}, indent=2))
