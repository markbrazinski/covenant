from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from src.obligations.candidate import (
    CANDIDATE_DELTA_SCHEMA,
    SYNTHETIC_APPROVAL_LABEL,
    activate_synthetic_test,
    active_candidate_policy,
    extract_candidate,
    extract_candidate_text,
    submit_for_review,
    validate_candidate,
)
from src.workflow import change_to_action

ROOT = Path(__file__).resolve().parents[1]
FIXED_TIME = datetime(2026, 8, 1, tzinfo=timezone.utc)


def canonical():
    candidate, documents = extract_candidate(
        ROOT / "fixtures" / "atlas_license_v3.md",
        ROOT / "fixtures" / "atlas_license_v4.md",
        now=lambda: FIXED_TIME,
    )
    validation = validate_candidate(candidate, documents, current_active_version=3)
    return candidate, documents, validation


def test_gate2_canonical_candidate_is_cited_and_not_self_activating():
    candidate, documents, validation = canonical()
    assert validation["valid"] is True
    assert candidate["lifecycle_state"] == "CANDIDATE"
    assert candidate["material_change"] is True
    assert not (set(CANDIDATE_DELTA_SCHEMA["required"]) - candidate.keys())
    assert candidate["usage_classes"] == {
        "permitted": ["internal_analytics"],
        "prohibited": ["customer_redistribution", "ml_training"],
        "review_required": ["anonymized_derivative"],
    }
    assert {
        item["usage_class"]: item["effect"] for item in candidate["rules"]
    } == {
        "internal_analytics": "permitted",
        "ml_training": "prohibited",
        "customer_redistribution": "prohibited",
        "anonymized_derivative": "review_required",
    }
    for rule in candidate["rules"]:
        citation = rule["citation"]
        assert citation["quote"] in documents[citation["source_ref"]]
        assert citation["source_sha256"] == candidate["source_documents"][1]["sha256"]


def test_gate2_review_and_synthetic_activation_are_separate_transitions():
    candidate, _, validation = canonical()
    awaiting, review = submit_for_review(
        candidate, validation, now=lambda: FIXED_TIME
    )
    assert review["prior_state"] == "CANDIDATE"
    assert review["new_state"] == awaiting["lifecycle_state"] == "AWAITING_REVIEW"
    with pytest.raises(ValueError, match="literal SYNTHETIC TEST APPROVAL"):
        activate_synthetic_test(
            awaiting,
            label="approved",
            actor="synthetic_gate2_reviewer",
            rationale="injected wrong label",
        )
    active, approval = activate_synthetic_test(
        awaiting,
        label=SYNTHETIC_APPROVAL_LABEL,
        actor="synthetic_gate2_reviewer",
        rationale="SYNTHETIC TEST APPROVAL only",
        now=lambda: FIXED_TIME,
    )
    assert approval["prior_state"] == "AWAITING_REVIEW"
    assert approval["new_state"] == active["lifecycle_state"] == "ACTIVE"
    assert approval["label"] == SYNTHETIC_APPROVAL_LABEL
    assert approval["actor_class"] == "synthetic_test_reviewer"


MATRIX = yaml.safe_load((ROOT / "fixtures" / "gate2_adversarial.yaml").read_text())


@pytest.mark.parametrize("case", MATRIX["cases"], ids=lambda case: case["id"])
def test_gate2_adversarial_document_matrix(case):
    old_ref = f"matrix:{case['id']}:old"
    new_ref = f"matrix:{case['id']}:new"
    candidate = extract_candidate_text(
        case["old_text"],
        case["new_text"],
        old_ref=old_ref,
        new_ref=new_ref,
        now=lambda: FIXED_TIME,
    )
    if case.get("mutation") == "citation_mismatch":
        candidate = deepcopy(candidate)
        target = next(
            item for item in candidate["rules"] if item["usage_class"] == "ml_training"
        )
        target["citation"]["quote"] = "- machine-learning training remains allowed;"
    validation = validate_candidate(
        candidate,
        {old_ref: case["old_text"], new_ref: case["new_text"]},
        current_active_version=case.get("current_active_version", 3),
    )
    assert validation["valid"] is case["expected_valid"]
    if case.get("expected_gap"):
        assert case["expected_gap"] in validation["errors"]
    if "expected_material_change" in case:
        assert candidate["material_change"] is case["expected_material_change"]
    if case["id"] == "prompt_injection_content":
        assert candidate["source_warnings"] == [
            "instruction_like_source_text_ignored"
        ]
        assert {
            item["usage_class"]: item["effect"] for item in candidate["rules"]
        }["ml_training"] == "prohibited"


def test_gate2_invalid_candidate_abstains_before_datahub_or_writeback(
    tmp_path, monkeypatch
):
    case = next(
        item for item in MATRIX["cases"] if item["id"] == "missing_effective_date"
    )
    old_path = tmp_path / "old.md"
    new_path = tmp_path / "new.md"
    old_path.write_text(case["old_text"])
    new_path.write_text(case["new_text"])

    def forbidden(*args, **kwargs):
        raise AssertionError("DataHub path must not run for an invalid candidate")

    monkeypatch.setattr(change_to_action, "analyse", forbidden)
    monkeypatch.setattr(change_to_action, "apply", forbidden)
    artifact = change_to_action.run_change_to_action(
        old_path, new_path, synthetic_approve=True
    )
    assert artifact["result"] == "ABSTAINED"
    assert artifact["candidate"]["lifecycle_state"] == "REJECTED"
    assert artifact["impact"] is None
    assert artifact["writeback"] is None


def test_gate2_no_material_change_creates_no_active_delta(tmp_path):
    case = next(item for item in MATRIX["cases"] if item["id"] == "no_material_change")
    old_path = tmp_path / "old.md"
    new_path = tmp_path / "new.md"
    old_path.write_text(case["old_text"])
    new_path.write_text(case["new_text"])
    artifact = change_to_action.run_change_to_action(
        old_path, new_path, synthetic_approve=True
    )
    assert artifact["result"] == "NO_MATERIAL_CHANGE"
    assert artifact["candidate"]["lifecycle_state"] == "REJECTED"
    assert artifact["impact"] is None
    assert artifact["writeback"] is None


def test_gate2_active_candidate_derives_locked_operational_policy():
    candidate, _, validation = canonical()
    awaiting, _ = submit_for_review(candidate, validation, now=lambda: FIXED_TIME)
    active, _ = activate_synthetic_test(
        awaiting,
        label=SYNTHETIC_APPROVAL_LABEL,
        actor="synthetic_gate2_reviewer",
        rationale="SYNTHETIC TEST APPROVAL only",
        now=lambda: FIXED_TIME,
    )
    policy = active_candidate_policy(active)
    assert {
        usage: rule["disposition"] for usage, rule in policy["rules"].items()
    } == {
        "internal_analytics": "allowed",
        "ml_training": "remediate",
        "customer_redistribution": "stop_proposed",
        "anonymized_derivative": "human_review",
    }
    assert policy["candidate_delta_id"] == candidate["candidate_delta_id"]
    assert policy["activation_id"].startswith("ACTIVATION-")


def test_gate2_runtime_does_not_read_expected_impact_fixture():
    for relative in (
        "src/obligations/candidate.py",
        "src/workflow/change_to_action.py",
        "scripts/run_change_to_action.py",
    ):
        text = (ROOT / relative).read_text()
        assert "expected_impact_report" not in text


def test_gate2_candidate_identity_is_stable_across_filesystem_locations(tmp_path):
    canonical_candidate, _, _ = canonical()
    old_copy = tmp_path / "old.md"
    new_copy = tmp_path / "new.md"
    old_copy.write_text((ROOT / "fixtures" / "atlas_license_v3.md").read_text())
    new_copy.write_text((ROOT / "fixtures" / "atlas_license_v4.md").read_text())
    copied_candidate, _ = extract_candidate(
        old_copy, new_copy, now=lambda: FIXED_TIME
    )
    assert copied_candidate["candidate_delta_id"] == canonical_candidate[
        "candidate_delta_id"
    ]
