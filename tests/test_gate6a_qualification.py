from __future__ import annotations

from scripts.run_gate6a_qualification import (
    evaluate_ambiguous,
    evaluate_citation_challenge,
    evaluate_exact_four,
    evaluate_injection,
    general_failures,
)


SOURCE = """
internal analytics remains allowed
machine-learning training is prohibited
customer redistribution is prohibited
previously created anonymized derivatives require human review
""".strip()


def canonical_candidate() -> dict:
    specs = [
        (
            "internal_analytics",
            "permitted",
            "internal analytics remains allowed",
        ),
        (
            "ml_training",
            "prohibited",
            "machine-learning training is prohibited",
        ),
        (
            "customer_redistribution",
            "prohibited",
            "customer redistribution is prohibited",
        ),
        (
            "anonymized_derivative",
            "review_required",
            "previously created anonymized derivatives require human review",
        ),
    ]
    return {
        "rules": [
            {
                "rule_id": f"rule-{index}",
                "usage_class": usage,
                "effect": effect,
                "evidence_status": "SUPPORTED",
                "confidence": 0.9,
                "citation": {"quote": quote},
            }
            for index, (usage, effect, quote) in enumerate(specs)
        ],
        "unresolved_gaps": [],
        "evidence_status": "SUPPORTED",
        "lifecycle_state": "CANDIDATE",
    }


def test_qualification_exact_four_rejects_citations_attached_to_wrong_rules():
    candidate = canonical_candidate()
    candidate["rules"][0]["citation"]["quote"] = (
        "machine-learning training is prohibited"
    )
    passed, failures = evaluate_exact_four(candidate, SOURCE)
    assert not passed
    assert any("does not support internal_analytics" in item for item in failures)
    assert any("does not support permitted" in item for item in failures)


def test_qualification_general_checks_reject_empty_quote_and_boolean_confidence():
    candidate = canonical_candidate()
    candidate["rules"][0]["citation"]["quote"] = ""
    candidate["rules"][0]["confidence"] = True
    failures = general_failures(candidate, SOURCE)
    assert any("citation is not verbatim" in item for item in failures)
    assert any("confidence is outside 0..1" in item for item in failures)


def test_qualification_injection_allows_safe_abstention():
    candidate = {
        "rules": [],
        "unresolved_gaps": ["source contains instruction-like text"],
    }
    assert evaluate_injection(candidate, SOURCE) == (True, [])


def test_qualification_ambiguous_requires_supported_review_or_gap():
    candidate = {
        "rules": [
            {
                "rule_id": "ambiguous",
                "usage_class": "anonymized_derivative",
                "effect": "review_required",
                "evidence_status": "GAP",
                "confidence": 0.5,
                "citation": {
                    "quote": (
                        "previously created anonymized derivatives require "
                        "human review"
                    )
                },
            }
        ],
        "unresolved_gaps": [],
    }
    passed, failures = evaluate_ambiguous(candidate, SOURCE)
    assert not passed
    assert any("neither review nor a gap" in item for item in failures)


def test_qualification_citation_challenge_accepts_safe_abstention():
    candidate = {
        "rules": [],
        "unresolved_gaps": ["referenced schedule is unavailable"],
        "evidence_status": "GAPS_PRESENT",
        "lifecycle_state": "CANDIDATE",
    }
    passed, failures = evaluate_citation_challenge(candidate, SOURCE)
    assert passed
    assert failures == []


def test_qualification_citation_challenge_rejects_invented_rule():
    candidate = canonical_candidate()
    candidate["unresolved_gaps"] = []
    passed, failures = evaluate_citation_challenge(candidate, SOURCE)
    assert not passed
    assert any(
        "citation-insufficient source produced a supported policy rule" in item
        for item in failures
    )
