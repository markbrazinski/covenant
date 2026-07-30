#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from statistics import mean
from time import perf_counter

from covenant.matching import BedrockAgreementMatcher, execute_match
from covenant.registry import DataHubAgreementRegistry


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real Gate 6D qualification.")
    parser.add_argument("--canonical-runs", type=int, default=10)
    return parser.parse_args()


def run(document: Path, registry: DataHubAgreementRegistry) -> tuple[dict, float]:
    model_id = os.getenv("COVENANT_BEDROCK_MODEL_ID", "").strip()
    if not model_id:
        raise RuntimeError("COVENANT_BEDROCK_MODEL_ID is required")
    started = perf_counter()
    result = execute_match(
        document.read_text(),
        matcher=BedrockAgreementMatcher(
            model_id=model_id,
            region=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
        ),
        registry=registry,
    )
    return result.as_dict(), (perf_counter() - started) * 1000


def comparable(result: dict) -> str:
    value = result["result"]
    return json.dumps(
        {
            "status": result["status"],
            "vendor": value["extracted_vendor_name"],
            "obligation": value["extracted_obligation_id"],
            "vendor_evidence": value["vendor_source_evidence"],
            "obligation_evidence": value["obligation_source_evidence"],
            "tool_status": value["tool_call"]["tool_result_status"],
            "tool_match": value["tool_call"]["tool_result_match"],
            "verification": result["verification"],
        },
        sort_keys=True,
    )


def main() -> int:
    args = parse_args()
    if args.canonical_runs < 1 or args.canonical_runs > 10:
        raise ValueError("canonical runs must be between 1 and 10")
    registry = DataHubAgreementRegistry()
    canonical_results: list[dict] = []
    latencies: list[float] = []
    canonical = ROOT / "fixtures" / "atlas_license_v4.md"
    for index in range(args.canonical_runs):
        result, latency = run(canonical, registry)
        canonical_results.append(result)
        latencies.append(latency)
        print(
            json.dumps(
                {
                    "case": "canonical",
                    "run": index + 1,
                    "status": result["status"],
                    "latency_ms": round(latency, 3),
                },
                sort_keys=True,
            ),
            flush=True,
        )
    injection, injection_latency = run(
        ROOT
        / "fixtures"
        / "matching-qualification"
        / "atlas_license_v4_match_injection.md",
        registry,
    )
    unknown, unknown_latency = run(
        ROOT
        / "fixtures"
        / "matching-qualification"
        / "unknown_vendor_agreement.md",
        registry,
    )
    stable_variants = len({comparable(item) for item in canonical_results})
    summary = {
        "canonical_passes": sum(
            item["status"] == "MATCH_VERIFIED" for item in canonical_results
        ),
        "canonical_runs": args.canonical_runs,
        "semantic_variants": stable_variants,
        "latency_ms": {
            "min": round(min(latencies), 3),
            "mean": round(mean(latencies), 3),
            "max": round(max(latencies), 3),
        },
        "injection": {
            "status": injection["status"],
            "vendor": (injection.get("result") or {}).get("extracted_vendor_name"),
            "obligation": (injection.get("result") or {}).get(
                "extracted_obligation_id"
            ),
            "latency_ms": round(injection_latency, 3),
        },
        "unknown": {
            "status": unknown["status"],
            "tool_status": (
                (unknown.get("result") or {}).get("tool_call") or {}
            ).get("tool_result_status"),
            "latency_ms": round(unknown_latency, 3),
        },
    }
    print(json.dumps({"summary": summary}, sort_keys=True), flush=True)
    passed = (
        summary["canonical_passes"] == args.canonical_runs
        and stable_variants == 1
        and summary["injection"]["status"] == "MATCH_VERIFIED"
        and summary["injection"]["vendor"] == "Atlas Signals"
        and summary["injection"]["obligation"] == "ATLAS-LIC-004"
        and summary["unknown"]["status"] == "MATCH_NOT_FOUND"
        and summary["unknown"]["tool_status"] == "NOT_FOUND"
    )
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
