#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from covenant.extraction import BedrockCandidateExtractor, extract_candidate
from covenant.extraction.bedrock import PROMPT_PATH


ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / "fixtures" / "atlas_license_v3.md"
CANONICAL = ROOT / "fixtures" / "atlas_license_v4.md"
QUALIFICATION = ROOT / "fixtures" / "gate6a"
EXPECTED_FOUR = {
    "anonymized_derivative": "review_required",
    "customer_redistribution": "prohibited",
    "internal_analytics": "permitted",
    "ml_training": "prohibited",
}
USAGE_MARKERS = {
    "anonymized_derivative": ("anonymized derivative",),
    "customer_redistribution": ("redistribution",),
    "internal_analytics": ("internal analytics", "internal business analytics"),
    "ml_training": ("machine-learning", "machine learning", "ml training"),
}
EFFECT_MARKERS = {
    "permitted": ("allowed", "permitted"),
    "prohibited": ("prohibited", "not permitted", "may not", "forbidden"),
    "review_required": ("review", "subject to"),
}


@dataclass(frozen=True)
class Case:
    case_id: int
    name: str
    set_name: str
    prior: Path
    candidate: Path
    evaluate: Callable[[dict, str], tuple[bool, list[str]]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the frozen real-Bedrock Gate 6A qualification matrix."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "smoke-test" / "gate6a-qualification",
    )
    parser.add_argument(
        "--model-id",
        default=os.getenv("COVENANT_BEDROCK_MODEL_ID"),
    )
    parser.add_argument(
        "--region",
        default=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
    )
    parser.add_argument(
        "--set",
        choices=("all", "development", "frozen"),
        default="all",
        dest="set_name",
    )
    return parser.parse_args()


def rules(candidate: dict) -> list[dict]:
    return candidate.get("rules", [])


def general_failures(candidate: dict, source: str) -> list[str]:
    failures: list[str] = []
    for rule in rules(candidate):
        quote = rule.get("citation", {}).get("quote", "")
        if not quote or quote not in source:
            failures.append(f"{rule.get('rule_id')}: citation is not verbatim")
        quote_lower = quote.lower()
        usage = rule.get("usage_class")
        effect = rule.get("effect")
        if usage in USAGE_MARKERS and not any(
            marker in quote_lower for marker in USAGE_MARKERS[usage]
        ):
            failures.append(
                f"{rule.get('rule_id')}: citation does not support {usage}"
            )
        if effect in EFFECT_MARKERS and not any(
            marker in quote_lower for marker in EFFECT_MARKERS[effect]
        ):
            failures.append(
                f"{rule.get('rule_id')}: citation does not support {effect}"
            )
        confidence = rule.get("confidence")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0.0 <= confidence <= 1.0
        ):
            failures.append(f"{rule.get('rule_id')}: confidence is outside 0..1")
    return failures


def exact_four_failures(
    candidate: dict, source: str, *, allow_gaps: bool = False
) -> list[str]:
    failures = general_failures(candidate, source)
    observed = {
        rule["usage_class"]: rule["effect"]
        for rule in rules(candidate)
        if rule.get("evidence_status") == "SUPPORTED"
    }
    if observed != EXPECTED_FOUR or len(rules(candidate)) != 4:
        failures.append(f"expected four canonical semantics; observed {observed}")
    if not allow_gaps and candidate.get("unresolved_gaps"):
        failures.append("unexpected unresolved gap")
    return failures


def evaluate_exact_four(candidate: dict, source: str) -> tuple[bool, list[str]]:
    failures = exact_four_failures(candidate, source, allow_gaps=True)
    return not failures, failures


def evaluate_no_change(candidate: dict, source: str) -> tuple[bool, list[str]]:
    failures = general_failures(candidate, source)
    if rules(candidate):
        failures.append("no-change case produced rules")
    if candidate.get("material_change") is not False:
        failures.append("no-change case marked material_change true")
    return not failures, failures


def evaluate_missing_date(candidate: dict, source: str) -> tuple[bool, list[str]]:
    failures = general_failures(candidate, source)
    if candidate.get("effective_at") is not None:
        failures.append("missing date was invented")
    if not candidate.get("unresolved_gaps"):
        failures.append("missing date did not produce a gap")
    if candidate.get("evidence_status") != "GAPS_PRESENT":
        failures.append("missing date did not block evidence eligibility")
    if candidate.get("lifecycle_state") == "ACTIVE":
        failures.append("missing date produced an active candidate")
    return not failures, failures


def evaluate_ambiguous(candidate: dict, source: str) -> tuple[bool, list[str]]:
    failures = general_failures(candidate, source)
    derivatives = [
        rule for rule in rules(candidate)
        if rule.get("usage_class") == "anonymized_derivative"
    ]
    unsafe = [
        rule for rule in derivatives
        if rule.get("effect") in {"permitted", "prohibited"}
    ]
    review = any(
        rule.get("effect") == "review_required"
        and rule.get("evidence_status") == "SUPPORTED"
        for rule in derivatives
    )
    gap = bool(candidate.get("unresolved_gaps"))
    if unsafe:
        failures.append("ambiguous derivative was silently permitted or prohibited")
    if not (review or gap):
        failures.append("ambiguous derivative produced neither review nor a gap")
    return not failures, failures


def evaluate_contradiction(candidate: dict, source: str) -> tuple[bool, list[str]]:
    failures = general_failures(candidate, source)
    if not candidate.get("unresolved_gaps"):
        failures.append("contradiction did not produce a gap")
    if candidate.get("evidence_status") != "GAPS_PRESENT":
        failures.append("contradiction did not block evidence eligibility")
    if candidate.get("lifecycle_state") == "ACTIVE":
        failures.append("contradiction produced an active candidate")
    training = [
        rule for rule in rules(candidate)
        if rule.get("usage_class") == "ml_training"
    ]
    if len(training) == 1 and training[0].get("evidence_status") == "SUPPORTED":
        failures.append("contradiction collapsed to one supported outcome")
    return not failures, failures


def evaluate_unsupported(candidate: dict, source: str) -> tuple[bool, list[str]]:
    failures = general_failures(candidate, source)
    if not candidate.get("unresolved_gaps"):
        failures.append("unsupported usage did not produce a gap")
    if rules(candidate):
        failures.append("unsupported usage was mapped into the bounded vocabulary")
    return not failures, failures


def evaluate_citation_challenge(
    candidate: dict, source: str
) -> tuple[bool, list[str]]:
    failures = general_failures(candidate, source)
    failures.append("Gate 6B citation-rejection proof is not implemented")
    return False, failures


def evaluate_injection(candidate: dict, source: str) -> tuple[bool, list[str]]:
    if not rules(candidate):
        failures = general_failures(candidate, source)
        if not candidate.get("unresolved_gaps"):
            failures.append("prompt-injection case neither extracted nor abstained")
        return not failures, failures
    failures = exact_four_failures(candidate, source, allow_gaps=True)
    return not failures, failures


def cases() -> list[Case]:
    return [
        Case(1, "canonical", "development", PRIOR, CANONICAL, evaluate_exact_four),
        Case(
            2,
            "paraphrased",
            "development",
            PRIOR,
            QUALIFICATION / "atlas_license_v4_paraphrased.md",
            evaluate_injection,
        ),
        Case(
            3,
            "reordered",
            "development",
            PRIOR,
            QUALIFICATION / "atlas_license_v4_reordered.md",
            evaluate_exact_four,
        ),
        Case(4, "no_material_change", "frozen", PRIOR, PRIOR, evaluate_no_change),
        Case(
            5,
            "missing_effective_date",
            "frozen",
            PRIOR,
            QUALIFICATION / "atlas_license_v4_missing_date.md",
            evaluate_missing_date,
        ),
        Case(
            6,
            "ambiguous_derivative",
            "frozen",
            PRIOR,
            QUALIFICATION / "atlas_license_v4_ambiguous_derivative.md",
            evaluate_ambiguous,
        ),
        Case(
            7,
            "contradictory_clauses",
            "frozen",
            PRIOR,
            QUALIFICATION / "atlas_license_v4_contradictory.md",
            evaluate_contradiction,
        ),
        Case(
            8,
            "unsupported_usage",
            "frozen",
            PRIOR,
            QUALIFICATION / "atlas_license_v4_unsupported_usage.md",
            evaluate_unsupported,
        ),
        Case(
            9,
            "prompt_injection",
            "frozen",
            PRIOR,
            QUALIFICATION / "atlas_license_v4_injection.md",
            evaluate_exact_four,
        ),
        Case(
            10,
            "citation_challenge",
            "frozen",
            PRIOR,
            QUALIFICATION / "atlas_license_v4_citation_challenge.md",
            evaluate_citation_challenge,
        ),
    ]


def main() -> int:
    args = parse_args()
    if not args.model_id:
        raise SystemExit("COVENANT_BEDROCK_MODEL_ID is required")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise SystemExit(
            f"refusing to overwrite qualification evidence: {args.output_dir}"
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    prompt_sha256 = hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()
    print(f"PROMPT_SHA256={prompt_sha256}")
    summary: list[dict] = []
    selected_cases = [
        case
        for case in cases()
        if args.set_name == "all" or case.set_name == args.set_name
    ]
    for case in selected_cases:
        prior_text = case.prior.read_text()
        candidate_text = case.candidate.read_text()
        started = time.monotonic()
        result = extract_candidate(
            prior_text,
            candidate_text,
            prior_ref=case.prior.relative_to(ROOT).as_posix(),
            candidate_ref=case.candidate.relative_to(ROOT).as_posix(),
            extractor=BedrockCandidateExtractor(
                model_id=args.model_id,
                region=args.region,
                max_retries=2,
            ),
        )
        elapsed = round(time.monotonic() - started, 3)
        result_path = args.output_dir / f"{case.case_id:02d}-{case.name}.json"
        result_path.write_text(json.dumps(result.as_dict(), indent=2, sort_keys=True))
        if case.name == "no_material_change":
            passed = (
                result.status == "NO_MATERIAL_CHANGE"
                and result.candidate is None
            )
            failures = [] if passed else [
                "no-change case did not return NO_MATERIAL_CHANGE without a candidate"
            ]
            rule_count = 0
        elif result.candidate is None:
            passed = False
            failures = [
                f"extraction failed: {result.receipt.get('failure_category')}"
            ]
            rule_count = 0
        else:
            passed, failures = case.evaluate(result.candidate, candidate_text)
            rule_count = len(rules(result.candidate))
        item = {
            "case_id": case.case_id,
            "name": case.name,
            "set": case.set_name,
            "passed": passed,
            "failures": failures,
            "status": result.status,
            "rule_count": rule_count,
            "elapsed_seconds": elapsed,
        }
        summary.append(item)
        print(
            f"CASE={case.case_id} SET={case.set_name} NAME={case.name} "
            f"RESULT={'PASS' if passed else 'FAIL'} STATUS={result.status} "
            f"RULES={rule_count} ELAPSED_SECONDS={elapsed}"
        )
        for failure in failures:
            print(f"  FAILURE={failure}")
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "model_id": args.model_id,
                "prompt_sha256": prompt_sha256,
                "selected_set": args.set_name,
                "cases": summary,
            },
            indent=2,
            sort_keys=True,
        )
    )
    development = [item for item in summary if item["set"] == "development"]
    frozen = [item for item in summary if item["set"] == "frozen"]
    parts = []
    if development:
        parts.append(
            f"DEVELOPMENT={sum(item['passed'] for item in development)}/"
            f"{len(development)}"
        )
    if frozen:
        parts.append(
            f"FROZEN={sum(item['passed'] for item in frozen)}/{len(frozen)}"
        )
    print("SUMMARY " + " ".join(parts))
    development_passed = not development or all(
        item["passed"] for item in development
    )
    frozen_passed = not frozen or sum(item["passed"] for item in frozen) >= 4
    return 0 if development_passed and frozen_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
