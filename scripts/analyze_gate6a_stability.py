#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED_USAGES = {
    "anonymized_derivative",
    "customer_redistribution",
    "internal_analytics",
    "ml_training",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze preserved Gate 6A canonical extraction runs."
    )
    parser.add_argument("results_dir", type=Path)
    parser.add_argument("--expected-runs", type=int, default=10)
    return parser.parse_args()


def semantic_signature(candidate: dict) -> str:
    semantics = sorted(
        (
            rule["usage_class"],
            rule["effect"],
            rule["evidence_status"],
            rule["citation"]["quote"],
        )
        for rule in candidate["rules"]
    )
    return hashlib.sha256(
        json.dumps(semantics, separators=(",", ":")).encode()
    ).hexdigest()


def main() -> int:
    args = parse_args()
    paths = sorted(
        args.results_dir.glob("run-*.json"),
        key=lambda path: int(path.stem.split("-")[1]),
    )
    results = [json.loads(path.read_text()) for path in paths]
    candidates = [
        result["candidate"]
        for result in results
        if result.get("status") == "EXTRACTED_UNVERIFIED"
        and result.get("candidate") is not None
    ]
    presence = {
        usage: sum(
            any(rule["usage_class"] == usage for rule in candidate["rules"])
            for candidate in candidates
        )
        for usage in sorted(EXPECTED_USAGES)
    }
    summary = {
        "run_count": len(results),
        "success_count": len(candidates),
        "candidate_id_variants": len(
            {candidate["candidate_delta_id"] for candidate in candidates}
        ),
        "semantic_variants": len(
            {semantic_signature(candidate) for candidate in candidates}
        ),
        "timestamp_variants": len(
            {
                candidate["extraction_metadata"]["extraction_completed_at"]
                for candidate in candidates
            }
        ),
        "token_variants": len(
            {
                (
                    candidate["extraction_metadata"]["input_token_count"],
                    candidate["extraction_metadata"]["output_token_count"],
                )
                for candidate in candidates
            }
        ),
        "usage_presence": presence,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    passed = (
        len(results) == args.expected_runs
        and len(candidates) == args.expected_runs
        and summary["candidate_id_variants"] == 1
        and summary["semantic_variants"] == 1
        and summary["timestamp_variants"] == args.expected_runs
        and all(count == args.expected_runs for count in presence.values())
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
