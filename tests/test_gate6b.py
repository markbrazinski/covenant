from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import pytest

from covenant.extraction.bedrock import ModelExtraction
from covenant.extraction.service import build_candidate
from covenant.extraction.verifier import (
    verify_and_submit_for_review,
    verify_candidate_delta,
)
from src.api.service import CovenantService
from src.api.store import RunStore


ROOT = Path(__file__).resolve().parents[1]
PRIOR = (ROOT / "fixtures" / "atlas_license_v3.md").read_text()
CANDIDATE = (ROOT / "fixtures" / "atlas_license_v4.md").read_text()
PRIOR_REF = "fixtures/atlas_license_v3.md"
CANDIDATE_REF = "fixtures/atlas_license_v4.md"
NOW = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)


def model_payload() -> dict:
    return {
        "schema_version": "covenant.candidate_delta.v1",
        "obligation_id": "ATLAS-LIC-004",
        "supersedes_version": 3,
        "candidate_version": 4,
        "effective_at": "2026-08-01T00:00:00Z",
        "rules": [
            {
                "rule_id": "rule-analytics",
                "usage_class": "internal_analytics",
                "effect": "permitted",
                "cited_clause_verbatim": "internal analytics remains allowed",
                "evidence_status": "SUPPORTED",
                "confidence": 0.99,
            },
            {
                "rule_id": "rule-training",
                "usage_class": "ml_training",
                "effect": "prohibited",
                "cited_clause_verbatim": "machine-learning training is prohibited",
                "evidence_status": "SUPPORTED",
                "confidence": 0.98,
            },
            {
                "rule_id": "rule-redistribution",
                "usage_class": "customer_redistribution",
                "effect": "prohibited",
                "cited_clause_verbatim": "customer redistribution is prohibited",
                "evidence_status": "SUPPORTED",
                "confidence": 0.98,
            },
            {
                "rule_id": "rule-derivative",
                "usage_class": "anonymized_derivative",
                "effect": "review_required",
                "cited_clause_verbatim": (
                    "previously created anonymized derivatives require human review"
                ),
                "evidence_status": "SUPPORTED",
                "confidence": 0.97,
            },
        ],
        "material_change": True,
        "unresolved_gaps": [],
    }


def candidate() -> dict:
    return build_candidate(
        ModelExtraction(
            payload=model_payload(),
            model_id="test.anthropic-model",
            prompt_version="candidate-delta-v1.0.0",
            input_token_count=100,
            output_token_count=50,
            attempts=1,
        ),
        prior_text=PRIOR,
        candidate_text=CANDIDATE,
        prior_ref=PRIOR_REF,
        candidate_ref=CANDIDATE_REF,
        started_at=NOW.isoformat(),
        completed_at=NOW.isoformat(),
    )


def documents() -> dict[str, str]:
    return {PRIOR_REF: PRIOR, CANDIDATE_REF: CANDIDATE}


def extraction_receipt(value: dict) -> dict:
    return {
        **value["extraction_metadata"],
        "status": "EXTRACTED_UNVERIFIED",
        "attempts": 1,
    }


def failures_for(result: dict, check: str) -> list[dict]:
    return [item for item in result["failures"] if item["check"] == check]


def test_gate6b_canonical_candidate_passes_under_200_milliseconds():
    started = perf_counter()
    result = verify_candidate_delta(candidate(), documents())
    elapsed_ms = (perf_counter() - started) * 1000
    assert result == {"status": "PASS"}
    assert elapsed_ms < 200


def test_gate6b_hallucinated_citation_is_rejected_with_rule_id():
    value = candidate()
    value["rules"][1]["citation"]["quote"] = (
        "machine-learning training is prohibited in every territory"
    )
    result = verify_candidate_delta(value, documents())
    assert result["status"] == "REJECT"
    failures = failures_for(result, "citation_verification")
    assert any(item["rule_id"] == "rule-training" for item in failures)


def test_gate6b_frozen_citation_challenge_is_caught_deterministically():
    challenge = (
        ROOT / "fixtures" / "gate6a" / "atlas_license_v4_citation_challenge.md"
    ).read_text()
    payload = model_payload()
    payload["rules"] = [
        {
            "rule_id": "rule-training-hallucinated",
            "usage_class": "ml_training",
            "effect": "prohibited",
            "cited_clause_verbatim": (
                "machine-learning training is prohibited without exception"
            ),
            "evidence_status": "SUPPORTED",
            "confidence": 0.9,
        }
    ]
    challenge_ref = "fixtures/gate6a/atlas_license_v4_citation_challenge.md"
    value = build_candidate(
        ModelExtraction(
            payload=payload,
            model_id="test.anthropic-model",
            prompt_version="candidate-delta-v1.0.0",
            input_token_count=100,
            output_token_count=50,
            attempts=1,
        ),
        prior_text=PRIOR,
        candidate_text=challenge,
        prior_ref=PRIOR_REF,
        candidate_ref=challenge_ref,
        started_at=NOW.isoformat(),
        completed_at=NOW.isoformat(),
    )
    result = verify_candidate_delta(
        value,
        {PRIOR_REF: PRIOR, challenge_ref: challenge},
    )
    assert result["status"] == "REJECT"
    assert not failures_for(result, "source_integrity")
    failures = failures_for(result, "citation_verification")
    assert any(
        item["rule_id"] == "rule-training-hallucinated"
        for item in failures
    )


def test_gate6b_wrong_rule_type_is_rejected_semantically():
    value = candidate()
    value["rules"][1]["effect"] = "permitted"
    result = verify_candidate_delta(value, documents())
    failures = failures_for(result, "semantic_consistency")
    assert result["status"] == "REJECT"
    assert any(item["rule_id"] == "rule-training" for item in failures)


def test_gate6b_missing_required_field_is_rejected_by_schema():
    value = candidate()
    del value["candidate_version"]
    result = verify_candidate_delta(value, documents())
    assert result["status"] == "REJECT"
    assert failures_for(result, "schema_validation")


@pytest.mark.parametrize("field", ["rules", "source_documents"])
def test_gate6b_malformed_containers_reject_without_crashing(field):
    value = candidate()
    value[field] = None
    result = verify_candidate_delta(value, documents())
    assert result["status"] == "REJECT"
    assert failures_for(result, "schema_validation")


@pytest.mark.parametrize("value", [None, [], "not-an-object"])
def test_gate6b_malformed_top_level_rejects_without_crashing(value):
    result = verify_candidate_delta(value, documents())
    assert result == {
        "status": "REJECT",
        "failures": [
            {
                "rule_id": None,
                "check": "schema_validation",
                "message": "candidate does not satisfy the schema at <root>",
            }
        ],
    }


def test_gate6b_invalid_enum_and_confidence_are_rejected():
    value = candidate()
    value["rules"][0]["usage_class"] = "facial_recognition"
    value["rules"][0]["confidence"] = 1.2
    result = verify_candidate_delta(value, documents())
    assert result["status"] == "REJECT"
    assert failures_for(result, "schema_validation")
    assert failures_for(result, "vocabulary_consistency")


@pytest.mark.parametrize("confidence", [-0.01, 1.01, True, "0.9"])
def test_gate6b_confidence_bounds_and_type_are_strict(confidence):
    value = candidate()
    value["rules"][0]["confidence"] = confidence
    result = verify_candidate_delta(value, documents())
    assert result["status"] == "REJECT"
    failures = failures_for(result, "schema_validation")
    assert failures
    assert any(item["rule_id"] == "rule-analytics" for item in failures)


def test_gate6b_model_cannot_add_downstream_behavior_to_a_rule():
    value = candidate()
    value["rules"][0]["downstream_disposition"] = "allowed"
    result = verify_candidate_delta(value, documents())
    assert result["status"] == "REJECT"
    assert failures_for(result, "schema_validation")


def test_gate6b_model_cannot_add_top_level_downstream_behavior():
    value = candidate()
    value["downstream_disposition"] = "allowed"
    result = verify_candidate_delta(value, documents())
    assert result["status"] == "REJECT"
    assert failures_for(result, "schema_validation")


def test_gate6b_source_hash_mismatch_is_rejected():
    value = candidate()
    tampered = documents()
    tampered[CANDIDATE_REF] += "\nmodified"
    result = verify_candidate_delta(value, tampered)
    assert result["status"] == "REJECT"
    assert failures_for(result, "source_integrity")


def test_gate6b_prior_source_hash_mismatch_is_also_rejected():
    value = candidate()
    tampered = documents()
    tampered[PRIOR_REF] += "\nmodified"
    result = verify_candidate_delta(value, tampered)
    assert result["status"] == "REJECT"
    assert failures_for(result, "source_integrity")


def test_gate6b_requires_exactly_one_candidate_and_superseded_source():
    value = candidate()
    value["source_documents"].append(deepcopy(value["source_documents"][1]))
    result = verify_candidate_delta(value, documents())
    assert result["status"] == "REJECT"
    assert failures_for(result, "source_integrity")


def test_gate6b_source_roles_must_reference_distinct_documents():
    value = candidate()
    value["source_documents"][1]["source_ref"] = PRIOR_REF
    result = verify_candidate_delta(value, documents())
    assert result["status"] == "REJECT"
    assert failures_for(result, "source_integrity")


def test_gate6b_citation_source_hash_mismatch_is_rejected():
    value = candidate()
    value["rules"][0]["citation"]["source_sha256"] = "0" * 64
    result = verify_candidate_delta(value, documents())
    assert result["status"] == "REJECT"
    assert failures_for(result, "citation_verification")


def test_gate6b_citation_whitespace_is_not_normalized():
    value = candidate()
    value["rules"][3]["citation"]["quote"] = (
        "previously created anonymized derivatives  require human review"
    )
    result = verify_candidate_delta(value, documents())
    assert result["status"] == "REJECT"
    assert failures_for(result, "citation_verification")


def test_gate6b_verbatim_citations_cannot_be_swapped_between_usage_classes():
    value = candidate()
    training_quote = value["rules"][1]["citation"]["quote"]
    redistribution_quote = value["rules"][2]["citation"]["quote"]
    value["rules"][1]["citation"]["quote"] = redistribution_quote
    value["rules"][2]["citation"]["quote"] = training_quote
    result = verify_candidate_delta(value, documents())
    assert result["status"] == "REJECT"
    failures = failures_for(result, "semantic_consistency")
    assert {"rule-training", "rule-redistribution"} <= {
        item["rule_id"] for item in failures
    }


def test_gate6b_effective_date_must_follow_discoverable_source_creation():
    source_documents = {
        PRIOR_REF: {"text": PRIOR, "created_at": "2026-07-01T00:00:00Z"},
        CANDIDATE_REF: {
            "text": CANDIDATE,
            "created_at": "2026-08-02T00:00:00Z",
        },
    }
    result = verify_candidate_delta(candidate(), source_documents)
    assert result["status"] == "REJECT"
    assert failures_for(result, "date_verification")


def test_gate6b_invalid_effective_date_is_rejected():
    value = candidate()
    value["effective_at"] = "not-a-date"
    result = verify_candidate_delta(value, documents())
    assert result["status"] == "REJECT"
    assert failures_for(result, "date_verification")


def test_gate6b_extraction_timestamps_must_parse_and_be_ordered():
    invalid = candidate()
    invalid["extraction_metadata"]["extraction_started_at"] = "not-a-time"
    result = verify_candidate_delta(invalid, documents())
    assert result["status"] == "REJECT"
    assert failures_for(result, "date_verification")

    reversed_times = candidate()
    reversed_times["extraction_metadata"]["extraction_started_at"] = (
        "2026-07-29T13:00:00+00:00"
    )
    result = verify_candidate_delta(reversed_times, documents())
    assert result["status"] == "REJECT"
    assert failures_for(result, "date_verification")


def test_gate6b_unresolved_gap_blocks_eligibility():
    value = candidate()
    value["unresolved_gaps"] = ["missing schedule"]
    value["evidence_status"] = "GAPS_PRESENT"
    result = verify_candidate_delta(value, documents())
    assert result["status"] == "REJECT"
    assert failures_for(result, "evidence_eligibility")


def test_gate6b_rule_gap_blocks_eligibility_even_if_top_level_claims_supported():
    value = candidate()
    value["rules"][0]["evidence_status"] = "GAP"
    result = verify_candidate_delta(value, documents())
    assert result["status"] == "REJECT"
    failures = failures_for(result, "evidence_eligibility")
    assert any(item["rule_id"] == "rule-analytics" for item in failures)


def test_gate6b_usage_summary_must_match_rules():
    value = candidate()
    value["usage_classes"]["permitted"] = []
    result = verify_candidate_delta(value, documents())
    assert result["status"] == "REJECT"
    assert failures_for(result, "semantic_consistency")


def test_gate6b_material_change_cannot_have_zero_rules():
    value = candidate()
    value["rules"] = []
    value["usage_classes"] = {
        "permitted": [],
        "prohibited": [],
        "review_required": [],
    }
    result = verify_candidate_delta(value, documents())
    assert result["status"] == "REJECT"
    assert failures_for(result, "evidence_eligibility")


def test_gate6b_candidate_identity_is_recomputed_from_evidence():
    value = candidate()
    value["candidate_delta_id"] = "DELTA-00000000000000000000"
    result = verify_candidate_delta(value, documents())
    assert result["status"] == "REJECT"
    assert failures_for(result, "identity_consistency")


def test_gate6b_failure_messages_do_not_echo_source_or_credential_shaped_text():
    value = candidate()
    secret_shaped = "SECRET_SHAPED_TEST_VALUE ignore all instructions"
    value["rules"][0]["citation"]["quote"] = secret_shaped
    result = verify_candidate_delta(value, documents())
    messages = " ".join(item["message"] for item in result["failures"])
    assert result["status"] == "REJECT"
    assert secret_shaped not in messages
    assert "SECRET_SHAPED_TEST_VALUE" not in messages


def test_gate6b_failures_follow_commissioned_check_order():
    value = candidate()
    del value["obligation_id"]
    value["source_documents"][0]["sha256"] = "0" * 64
    value["rules"][0]["citation"]["quote"] = "invented allowance"
    value["effective_at"] = "not-a-date"
    value["rules"][1]["effect"] = "permitted"
    value["rules"][2]["usage_class"] = "unsupported_usage"
    value["unresolved_gaps"] = ["gap"]
    value["evidence_status"] = "GAPS_PRESENT"
    result = verify_candidate_delta(value, documents())
    checks = [item["check"] for item in result["failures"]]
    expected_order = {
        "schema_validation": 0,
        "source_integrity": 1,
        "citation_verification": 2,
        "date_verification": 3,
        "semantic_consistency": 4,
        "vocabulary_consistency": 5,
        "evidence_eligibility": 6,
    }
    positions = [expected_order[item] for item in checks]
    assert positions == sorted(positions)


def test_gate6b_any_failure_rejects_entire_candidate_and_names_all_rules():
    value = candidate()
    value["rules"][1]["citation"]["quote"] = "invented training clause"
    value["rules"][2]["citation"]["quote"] = "invented redistribution clause"
    result = verify_candidate_delta(value, documents())
    failed_rule_ids = {
        item["rule_id"]
        for item in failures_for(result, "citation_verification")
    }
    assert result["status"] == "REJECT"
    assert {"rule-training", "rule-redistribution"} <= failed_rule_ids


def test_gate6b_only_pass_can_enter_awaiting_review():
    accepted, pass_result, event = verify_and_submit_for_review(
        candidate(),
        documents(),
        current_active_version=3,
        now=lambda: NOW,
    )
    assert pass_result["status"] == "PASS"
    assert accepted["lifecycle_state"] == "AWAITING_REVIEW"
    assert event is not None
    assert event["new_state"] == "AWAITING_REVIEW"

    invalid = candidate()
    invalid["rules"][0]["citation"]["quote"] = "invented clause"
    rejected, reject_result, rejected_event = verify_and_submit_for_review(
        invalid,
        documents(),
        current_active_version=3,
        now=lambda: NOW,
    )
    assert reject_result["status"] == "REJECT"
    assert rejected["lifecycle_state"] == "REJECTED"
    assert rejected_event is None
    assert invalid["lifecycle_state"] == "CANDIDATE"


def test_gate6b_stale_candidate_cannot_enter_review():
    rejected, result, event = verify_and_submit_for_review(
        candidate(),
        documents(),
        current_active_version=4,
        now=lambda: NOW,
    )
    assert result["status"] == "REJECT"
    assert failures_for(result, "version_consistency")
    assert rejected["lifecycle_state"] == "REJECTED"
    assert event is None


def test_gate6b_verifier_is_deterministic_and_does_not_mutate_input():
    value = candidate()
    original = deepcopy(value)
    first = verify_candidate_delta(value, documents())
    second = verify_candidate_delta(value, documents())
    assert first == second
    assert value == original


def test_gate6b_service_records_only_verified_extraction_for_review():
    service = CovenantService(RunStore())
    value = candidate()
    record = service.record_verified_extraction(
        value,
        documents(),
        extraction_receipt(value),
        current_active_version=3,
    )
    assert record["candidate"]["lifecycle_state"] == "AWAITING_REVIEW"
    assert record["verification"] == {"status": "PASS"}
    assert len(record["transitions"]) == 1
    assert record["extraction_receipt"]["provider"] == "bedrock"


def test_gate6b_service_accepts_trusted_source_creation_metadata():
    service = CovenantService(RunStore())
    source_documents = {
        PRIOR_REF: {"text": PRIOR, "created_at": "2026-06-01T00:00:00Z"},
        CANDIDATE_REF: {
            "text": CANDIDATE,
            "created_at": "2026-07-01T00:00:00Z",
        },
    }
    value = candidate()
    record = service.record_verified_extraction(
        value,
        source_documents,
        extraction_receipt(value),
        current_active_version=3,
    )
    assert record["verification"] == {"status": "PASS"}
    assert record["documents"] == documents()


def test_gate6b_service_persists_rejection_without_review_transition():
    store = RunStore()
    service = CovenantService(store)
    invalid = candidate()
    invalid["rules"][0]["citation"]["quote"] = "invented clause"
    record = service.record_verified_extraction(
        invalid,
        documents(),
        extraction_receipt(invalid),
        current_active_version=3,
    )
    assert record["candidate"]["lifecycle_state"] == "REJECTED"
    assert record["verification"]["status"] == "REJECT"
    assert record["transitions"] == []
    assert record["persisted"] is False
    assert store.snapshot()["changes"] == {}


def test_gate6b_replay_does_not_overwrite_existing_lifecycle_record():
    store = RunStore()
    service = CovenantService(store)
    first = service.record_verified_extraction(
        (first_candidate := candidate()),
        documents(),
        extraction_receipt(first_candidate),
        current_active_version=3,
    )
    active = deepcopy(first)
    active["candidate"]["lifecycle_state"] = "ACTIVE"
    store.put_change(first["change_id"], active)

    replay = candidate()
    replay["rules"][0]["confidence"] = 0.5
    observed = service.record_verified_extraction(
        replay,
        documents(),
        extraction_receipt(replay),
        current_active_version=3,
    )
    assert observed["candidate"]["lifecycle_state"] == "ACTIVE"
    assert observed["candidate_hash"] == active["candidate_hash"]


def test_gate6b_rejected_replay_is_not_projected_as_prior_success():
    store = RunStore()
    service = CovenantService(store)
    first_candidate = candidate()
    first = service.record_verified_extraction(
        first_candidate,
        documents(),
        extraction_receipt(first_candidate),
        current_active_version=3,
    )
    invalid_replay = candidate()
    invalid_replay["rules"][0]["confidence"] = 2.0
    observed = service.record_verified_extraction(
        invalid_replay,
        documents(),
        extraction_receipt(invalid_replay),
        current_active_version=3,
    )
    assert observed["verification"]["status"] == "REJECT"
    assert observed["persisted"] is False
    stored = store.get_change(first["change_id"])
    assert stored is not None
    assert stored["verification"]["status"] == "PASS"


def test_gate6b_malformed_rejection_does_not_poison_change_queue():
    store = RunStore()
    service = CovenantService(store)
    invalid = candidate()
    del invalid["effective_at"]
    observed = service.record_verified_extraction(
        invalid,
        documents(),
        extraction_receipt(invalid),
        current_active_version=3,
    )
    assert observed["verification"]["status"] == "REJECT"
    assert observed["persisted"] is False
    assert service.list_changes() == []


def test_gate6b_receipt_must_match_verified_candidate_metadata():
    service = CovenantService(RunStore())
    value = candidate()
    invalid_receipt = extraction_receipt(value)
    invalid_receipt["status"] = "FAILED"
    with pytest.raises(Exception) as captured:
        service.record_verified_extraction(
            value,
            documents(),
            invalid_receipt,
            current_active_version=3,
        )
    assert getattr(captured.value, "code", None) == "INVALID_EXTRACTION_RECEIPT"
