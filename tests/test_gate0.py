from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from datahub.metadata.schema_classes import DatasetPropertiesClass, GlobalTagsClass

from src.datahub_client.core import dataset_urn, entity_urn, graph
from src.policy.engine import evaluate, load_policy, stable_decision_id
from src.reconciler.writeback import PREFIX, apply, desired_properties, readback
from src.workflow.impact import attach_paths, validate_active_version

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def actual():
    return json.loads((ROOT / "smoke-test" / "actual_impact_report.json").read_text())


def test_01_happy_path_exact_counts(actual):
    assert actual["counts"] == {
        "allowed": 1,
        "human_review": 1,
        "remediate": 2,
        "stop_proposed": 1,
        "unaffected": 1,
    }
    assert all(item["lineage_paths"] for item in actual["decisions"])
    assert {item["entity_type"] for item in actual["decisions"]} == {
        "dashboard",
        "dataJob",
        "dataset",
        "mlModel",
    }
    assert sum(item["entity_type"] == "mlModel" for item in actual["decisions"]) == 2
    assert {
        entity_urn("executive_dashboard"),
        entity_urn("churn_model_a"),
        entity_urn("propensity_model_b"),
        entity_urn("customer_delivery_job"),
    }.issubset({item["asset_urn"] for item in actual["decisions"]})


def test_02_rename_resistance():
    policy = load_policy()
    before = evaluate("urn:stable", {"usage_class": "ml_training", "owner": "group"}, policy)
    after = evaluate("urn:stable", {"usage_class": "ml_training", "owner": "group", "display_name": "renamed"}, policy)
    assert before == after


def test_03_semantic_usage_change_changes_disposition():
    first = evaluate("urn:stable", {"usage_class": "internal_analytics", "owner": "group"})
    changed = evaluate("urn:stable", {"usage_class": "ml_training", "owner": "group"})
    assert first["proposed_disposition"] == "allowed"
    assert changed["proposed_disposition"] == "remediate"


def test_04_unrelated_control_absent_and_unmutated(actual):
    control = dataset_urn("unrelated_control")
    assert control not in {item["asset_urn"] for item in actual["decisions"]}
    props = graph().get_aspect(control, DatasetPropertiesClass).customProperties
    assert not any(key.startswith(PREFIX) for key in props)
    tags = graph().get_aspect(control, GlobalTagsClass).tags
    assert not any("CovenantDisposition_" in item.tag for item in tags)


def test_05_multi_path_deduplicates_decision_and_preserves_paths():
    decision = evaluate("urn:terminal", {"usage_class": "ml_training", "owner": "group"})
    result = attach_paths(
        decision,
        {"paths": [{"path": [{"urn": "urn:source"}, {"urn": "urn:a"}, {"urn": "urn:terminal"}]}, {"path": [{"urn": "urn:source"}, {"urn": "urn:b"}, {"urn": "urn:terminal"}]}]},
    )
    assert result["asset_urn"] == "urn:terminal"
    assert len(result["lineage_paths"]) == 2


def test_06_missing_usage_never_allowed():
    result = evaluate("urn:x", {"owner": "group"})
    assert result["proposed_disposition"] == "human_review"
    assert "missing_usage_class" in result["evidence_gaps"]


def test_07_missing_owner_is_gap_not_invented():
    result = evaluate("urn:x", {"usage_class": "internal_analytics"})
    assert result["ownership_gap"] is True
    assert result["decision_owner"] is None


def test_08_broken_lineage_is_explicit_coverage_gap():
    result = attach_paths(evaluate("urn:x", {"usage_class": "ml_training", "owner": "group"}), {"paths": []})
    assert "missing_confirmed_lineage_path" in result["evidence_gaps"]


def test_09_read_only_reports_proposal_without_mutation(actual):
    result = apply(actual["decisions"], read_only=True)
    assert result == {"mode": "read_only", "proposed": 5, "written": 0, "verified": False}


def test_10_idempotent_identity_and_timestamp_reuse(actual):
    decision = actual["decisions"][0]
    assert stable_decision_id("ATLAS-LIC-004", 4, decision["asset_urn"]) == decision["decision_id"]
    existing = {PREFIX + "recorded_at": "stable-time"}
    assert desired_properties(decision, existing)[PREFIX + "recorded_at"] == "stable-time"


def test_11_stale_obligation_rejected():
    with pytest.raises(RuntimeError, match="stale"):
        validate_active_version(3, 4)
    validate_active_version(4, 4)


def test_12_partial_write_retry_converges(actual):
    with pytest.raises(RuntimeError, match="partial-write"):
        apply(actual["decisions"], fail_after=2)
    assert apply(actual["decisions"])["written"] == 5
    assert readback(actual["decisions"])["verified"] is True


def test_13_synthetic_human_override_is_distinguishable():
    evidence = json.loads((ROOT / "smoke-test" / "writeback_readback.json").read_text())
    override = evidence["synthetic_override"]
    assert override["label"] == "SYNTHETIC TEST APPROVAL"
    assert override["actor"] == "synthetic_gate1a_reviewer"
    assert override["prior_state"] != override["new_state"]
    assert "no real governance decision" in override["rationale"]
