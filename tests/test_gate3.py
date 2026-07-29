from __future__ import annotations

import json
import stat
from datetime import datetime
from pathlib import Path

import anyio
import httpx
import pytest
from pydantic import ValidationError

from src.api.app import configured_state_path, create_app
from src.api.schemas import WritebackEntityEvent
from src.api.service import CovenantService, datahub_entity_url
from src.api.store import RunStore
from src.obligations.candidate import SYNTHETIC_APPROVAL_LABEL
from src.reconciler.writeback import apply_one, readback
from src.workflow.impact import ImpactUnavailableError

ROOT = Path(__file__).resolve().parents[1]


class ASGIClient:
    def __init__(self, service: CovenantService | None = None) -> None:
        self.app = create_app(state_path=None, service=service)

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://covenant.test"
            ) as client:
                return await client.request(method, path, **kwargs)

        return anyio.run(send)

    def get(self, path: str, **kwargs) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response:
        return self.request("POST", path, **kwargs)


def client_for(service: CovenantService | None = None) -> ASGIClient:
    return ASGIClient(service)


def activation_payload(change: dict) -> dict:
    return {
        "reviewed_candidate_hash": change["candidate_hash"],
        "label": SYNTHETIC_APPROVAL_LABEL,
        "actor": "synthetic_gate3_reviewer",
        "review_note": "Gate 3 HTTP software test only; no real approval.",
    }


def test_gate3_candidate_only_http_path_and_schema_have_no_expected_outputs():
    client = client_for()
    response = client.get("/api/changes")
    assert response.status_code == 200
    changes = response.json()
    assert len(changes) == 1
    assert changes[0]["lifecycle_state"] == "AWAITING_REVIEW"
    assert changes[0]["material_rule_count"] == 4
    assert len(changes[0]["candidate_hash"]) == 64
    schema_text = json.dumps(client.get("/openapi.json").json())
    assert "expected_outputs" not in schema_text
    assert "expected_terminals" not in schema_text
    assert "expected_dispositions" not in schema_text


def test_gate3_cors_is_narrow_to_the_documented_development_origin():
    response = client_for().request(
        "OPTIONS",
        "/api/changes",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    refused = client_for().request(
        "OPTIONS",
        "/api/changes",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in refused.headers


def test_gate3_rejects_wildcard_cors(monkeypatch):
    monkeypatch.setenv("COVENANT_CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="wildcard"):
        create_app(state_path=None)


def test_gate3_state_override_stays_in_ignored_generated_state():
    safe = configured_state_path(
        "smoke-test/generated-state/operator-selected-state.json"
    )
    assert safe == ROOT / "smoke-test/generated-state/operator-selected-state.json"
    with pytest.raises(RuntimeError, match="smoke-test/generated-state"):
        configured_state_path("src/operator-selected-state.json")
    with pytest.raises(RuntimeError, match="smoke-test/generated-state"):
        configured_state_path("/tmp/operator-selected-state.json")


def test_gate3_datahub_links_require_safe_http_base(monkeypatch):
    urn = "urn:li:dashboard:(covenant,northstar.executive_dashboard)"
    monkeypatch.setenv("DATAHUB_UI_URL", "javascript://example.test")
    assert datahub_entity_url(urn, "dashboard") is None
    monkeypatch.setenv("DATAHUB_UI_URL", "https://user:pass@example.test")
    assert datahub_entity_url(urn, "dashboard") is None
    monkeypatch.setenv("DATAHUB_UI_URL", "https://datahub.example.test")
    assert datahub_entity_url(urn, "dashboard") == (
        "https://datahub.example.test/dashboard/"
        "urn:li:dashboard:(covenant,northstar.executive_dashboard)/"
    )
    assert datahub_entity_url(
        "urn:li:mlModel:(urn:li:dataPlatform:covenant,northstar.churn_model_a,DEV)",
        "mlModel",
    ) == (
        "https://datahub.example.test/mlModels/"
        "urn:li:mlModel:(urn:li:dataPlatform:covenant,northstar.churn_model_a,DEV)/"
    )
    assert datahub_entity_url(
        "urn:li:dataJob:(urn:li:dataFlow:(covenant,northstar.flow,DEV),northstar.job)",
        "dataJob",
    ) == (
        "https://datahub.example.test/tasks/"
        "urn:li:dataJob:(urn:li:dataFlow:(covenant,northstar.flow,DEV),northstar.job)/"
    )
    assert datahub_entity_url("urn:li:dataFlow:test", "dataFlow") is None


def test_gate3_readback_rejects_duplicate_identity_rows(monkeypatch):
    import src.reconciler.writeback as writeback

    decisions = [
        {
            "asset_urn": "urn:expected:one",
            "decision_id": "decision-one",
            "proposed_disposition": "allowed",
        },
        {
            "asset_urn": "urn:expected:two",
            "decision_id": "decision-two",
            "proposed_disposition": "remediate",
        },
    ]
    duplicate = {"urn": "urn:expected:one", "tags": {"tags": []}}
    monkeypatch.setattr(
        writeback,
        "call_mcp",
        lambda _: [{"result": [duplicate, duplicate]}],
    )
    monkeypatch.setattr(
        writeback,
        "property_contract",
        lambda _: (object, "dataset"),
    )
    monkeypatch.setattr(
        writeback,
        "native_custom_properties",
        lambda _: {
            writeback.PREFIX + "id": "decision-one",
            writeback.PREFIX + "state": "awaiting_human_approval",
        },
    )
    result = writeback.readback(decisions)
    assert result["identity_set_verified"] is False
    assert result["verified"] is False
    assert result["count"] == 1


def test_gate3_impact_is_blocked_before_activation():
    client = client_for()
    change = client.get("/api/changes").json()[0]
    response = client.post(f"/api/changes/{change['change_id']}/impact")
    assert response.status_code == 409
    assert response.json()["code"] == "ACTIVATION_REQUIRED"


def test_gate3_activation_requires_current_hash_and_literal_synthetic_label():
    client = client_for()
    change = client.get("/api/changes").json()[0]
    wrong_hash = activation_payload(change)
    wrong_hash["reviewed_candidate_hash"] = "0" * 64
    response = client.post(
        f"/api/changes/{change['change_id']}/activate", json=wrong_hash
    )
    assert response.status_code == 409
    assert response.json()["code"] == "CANDIDATE_HASH_MISMATCH"

    wrong_label = activation_payload(change)
    wrong_label["label"] = "approved"
    response = client.post(
        f"/api/changes/{change['change_id']}/activate", json=wrong_label
    )
    assert response.status_code == 409
    assert response.json()["code"] == "ACTIVATION_REFUSED"


def test_gate3_invalid_uploaded_change_cannot_activate():
    old_text = (ROOT / "fixtures" / "atlas_license_v3.md").read_text()
    new_text = (ROOT / "fixtures" / "atlas_license_v4.md").read_text().replace(
        "Effective August 1, 2026 for the fictional `vendor_demographics_raw` source:\n\n",
        "",
    )
    client = client_for()
    result = client.post(
        "/api/changes/analyze", json={"old_text": old_text, "new_text": new_text}
    )
    assert result.status_code == 200
    change = result.json()
    assert change["lifecycle_state"] == "REJECTED"
    response = client.post(
        f"/api/changes/{change['change_id']}/activate",
        json=activation_payload(change),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "ACTIVATION_REFUSED"


def test_gate3_mcp_outage_projects_unavailable_without_affected_set():
    def outage(policy):
        raise ImpactUnavailableError(
            "live DataHub MCP unavailable; Covenant did not produce an affected set"
        )

    service = CovenantService(RunStore(), impact_fn=outage)
    client = client_for(service)
    change = client.get("/api/changes").json()[0]
    activation = client.post(
        f"/api/changes/{change['change_id']}/activate",
        json=activation_payload(change),
    ).json()
    stale = service.store.get_run(activation["run_id"])
    stale["impact"] = {"counts": {"allowed": 99}, "decisions": []}
    stale["receipts"] = [{"asset_urn": "urn:stale", "recorded_at": "stale"}]
    service.store.put_run(activation["run_id"], stale)
    response = client.post(f"/api/changes/{change['change_id']}/impact")
    assert response.status_code == 503
    assert response.json() == {
        "code": "IMPACT_UNAVAILABLE",
        "message": "live DataHub MCP unavailable; Covenant did not produce an affected set",
        "affected_set_produced": False,
        "retryable": True,
    }
    events = client.get(f"/api/runs/{activation['run_id']}/events").json()
    assert events["error"]["affected_set_produced"] is False
    run = client.get(f"/api/runs/{activation['run_id']}").json()
    assert run["counts"] is None
    assert run["decisions"] == []
    assert run["receipts"] == []


def test_gate3_file_store_is_ignored_shape_and_owner_only(tmp_path):
    path = tmp_path / "state" / "gate3.json"
    store = RunStore(path)
    service = CovenantService(store)
    service.ensure_canonical_change()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    reloaded = RunStore(path).snapshot()
    assert reloaded["schema_version"] == "covenant.api_state.v1"
    assert len(reloaded["changes"]) == 1


@pytest.fixture(scope="module")
def live_http_result():
    client = client_for()
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["datahub"] == "connected"
    change = client.get("/api/changes").json()[0]
    activation = client.post(
        f"/api/changes/{change['change_id']}/activate",
        json=activation_payload(change),
    )
    assert activation.status_code == 200
    run_id = activation.json()["run_id"]
    impact = client.post(f"/api/changes/{change['change_id']}/impact")
    assert impact.status_code == 200
    assert impact.json()["receipts"] == []
    written = client.post(f"/api/runs/{run_id}/writeback")
    assert written.status_code == 200
    progress = client.get(f"/api/runs/{run_id}/writeback-progress")
    assert progress.status_code == 200
    replay = client.post(f"/api/runs/{run_id}/replay")
    assert replay.status_code == 200
    replay_progress = client.get(f"/api/runs/{run_id}/writeback-progress")
    assert replay_progress.status_code == 200
    return (
        impact.json(),
        written.json(),
        progress.json(),
        replay.json(),
        replay_progress.json(),
    )


def test_gate3_canonical_http_flow_uses_live_mcp_and_sdk(live_http_result):
    impact, written, _, _, _ = live_http_result
    assert impact["counts"] == {
        "allowed": 1,
        "human_review": 1,
        "remediate": 2,
        "stop_proposed": 1,
        "unaffected": 1,
    }
    assert impact["stage"] == "IMPACT_READY"
    assert len(impact["decisions"]) == 5
    assert all(item["mcp_path_verified"] for item in impact["decisions"])
    assert impact["graph"] == {
        "downstream_entity_count": 11,
        "terminal_count": 5,
        "read_interface": "mcp-server-datahub 0.6.0 live MCP",
    }
    assert [item["path_id"] for item in impact["decisions"]] == [
        "P1",
        "P2",
        "P3",
        "P4",
        "P5",
    ]
    assert all(item["path_nodes"] for item in impact["decisions"])
    assert impact["unaffected_control"]["unmutated_verified"] is False
    assert written["stage"] == "VERIFIED"
    assert written["reconciliation_verified"] is True
    assert len(written["receipts"]) == 5
    assert all(item["written"] for item in written["receipts"])
    assert all(not item["duplicate_tags"] for item in written["receipts"])
    assert written["unaffected_control"]["unmutated_verified"] is True


def test_gate3_http_replay_preserves_ids_and_timestamps(live_http_result):
    _, written, _, replay, replay_progress = live_http_result
    before = {item["decision_id"]: item for item in written["receipts"]}
    after = {item["decision_id"]: item for item in replay["receipts"]}
    assert before.keys() == after.keys()
    assert all(before[key]["recorded_at"] == after[key]["recorded_at"] for key in before)
    assert all(item["stable_recorded_at"] for item in replay["receipts"])
    assert all(not item["duplicate_tags"] for item in replay["receipts"])
    assert replay_progress["terminal"] is True
    assert replay_progress["failed"] is False
    assert [event["phase"] for event in replay_progress["events"]] == [
        "VERIFIED"
    ] * 5
    assert {
        event["entity_id"]: datetime.fromisoformat(
            event["phase_started_at"].replace("Z", "+00:00")
        )
        for event in replay_progress["events"]
    } == {
        item["decision_id"]: datetime.fromisoformat(item["recorded_at"])
        for item in replay["receipts"]
    }


def test_gate3_writeback_event_contract_validates_every_phase():
    phases = [
        "PENDING",
        "WRITING",
        "WRITTEN",
        "VERIFYING_MCP",
        "MCP_VERIFIED",
        "VERIFYING_SDK",
        "SDK_VERIFIED",
        "VERIFIED",
        "FAILED",
    ]
    for phase in phases:
        response_id = (
            "COV-RESPONSE-1"
            if phase
            not in {
                "PENDING",
                "WRITING",
            }
            else None
        )
        event = WritebackEntityEvent.model_validate(
            {
                "run_id": "RUN-1",
                "entity_id": "DECISION-1",
                "terminal_display_name": "Terminal",
                "sequence_index": 1,
                "phase": phase,
                "phase_started_at": "2026-07-29T12:00:00+00:00",
                "response_id": response_id,
                "failure": (
                    {
                        "category": "PARTIAL_WRITE",
                        "safe_message": "Native DataHub proposal write failed",
                    }
                    if phase == "FAILED"
                    else None
                ),
            }
        )
        assert event.phase == phase
    with pytest.raises(ValidationError):
        WritebackEntityEvent.model_validate(
            {
                "run_id": "RUN-1",
                "entity_id": "DECISION-1",
                "terminal_display_name": "Terminal",
                "sequence_index": 1,
                "phase": "VERIFIED",
                "phase_started_at": "2026-07-29T12:00:00+00:00",
                "response_id": None,
                "failure": None,
            }
        )


def test_gate3_writeback_progress_is_sequential_and_complete(live_http_result):
    _, _, progress, _, _ = live_http_result
    expected_phases = [
        "PENDING",
        "WRITING",
        "WRITTEN",
        "VERIFYING_MCP",
        "MCP_VERIFIED",
        "VERIFYING_SDK",
        "SDK_VERIFIED",
        "VERIFIED",
    ]
    entity_ids = [
        event["entity_id"]
        for event in progress["events"]
        if event["phase"] == "PENDING"
    ]
    assert len(entity_ids) == 5
    assert len(set(entity_ids)) == 5
    for sequence_index, entity_id in enumerate(entity_ids, start=1):
        entity_events = [
            event
            for event in progress["events"]
            if event["entity_id"] == entity_id
        ]
        assert [event["phase"] for event in entity_events] == expected_phases
        assert {event["sequence_index"] for event in entity_events} == {
            sequence_index
        }
        assert all(
            WritebackEntityEvent.model_validate(event) for event in entity_events
        )
    active_events = [
        event for event in progress["events"] if event["phase"] != "PENDING"
    ]
    assert [
        event["entity_id"]
        for event in active_events
        if event["phase"] == "WRITING"
    ] == entity_ids
    for previous, current in zip(entity_ids, entity_ids[1:]):
        previous_verified = next(
            index
            for index, event in enumerate(active_events)
            if event["entity_id"] == previous and event["phase"] == "VERIFIED"
        )
        current_writing = next(
            index
            for index, event in enumerate(active_events)
            if event["entity_id"] == current and event["phase"] == "WRITING"
        )
        assert previous_verified < current_writing
    assert progress["terminal"] is True
    assert progress["failed"] is False
    assert [event["phase"] for event in progress["entities"]] == [
        "VERIFIED"
    ] * 5


def test_gate3_partial_write_is_visible_and_retry_converges():
    apply_calls = []
    failed_once = False
    readback_calls = 0

    def interrupt_third_once(decision):
        nonlocal failed_once
        apply_calls.append(decision["decision_id"])
        if len(apply_calls) == 3 and not failed_once:
            failed_once = True
            raise RuntimeError("injected third-entity write failure")
        apply_one(decision)

    def project_partial_once(decisions):
        nonlocal readback_calls
        readback_calls += 1
        result = readback(decisions)
        if readback_calls == 1:
            for state in result["states"][2:]:
                state["mcp_tags_verified"] = False
                state["sdk_receipt_verified"] = False
        return result

    service = CovenantService(
        RunStore(),
        apply_one_fn=interrupt_third_once,
        readback_fn=project_partial_once,
    )
    client = client_for(service)
    change = client.get("/api/changes").json()[0]
    run = client.post(
        f"/api/changes/{change['change_id']}/activate",
        json=activation_payload(change),
    ).json()
    assert client.post(f"/api/changes/{change['change_id']}/impact").status_code == 200
    interrupted = client.post(f"/api/runs/{run['run_id']}/writeback")
    assert interrupted.status_code == 503
    assert interrupted.json()["code"] == "PARTIAL_WRITE"
    state = client.get(f"/api/runs/{run['run_id']}").json()
    assert state["stage"] == "PARTIAL_WRITE"
    assert state["reconciliation_verified"] is False
    assert len(state["receipts"]) == 5
    assert sum(item["sdk_receipt_readback_verified"] for item in state["receipts"]) == 2
    progress = client.get(
        f"/api/runs/{run['run_id']}/writeback-progress"
    ).json()
    assert progress["terminal"] is True
    assert progress["failed"] is True
    assert [entity["phase"] for entity in progress["entities"]] == [
        "VERIFIED",
        "VERIFIED",
        "FAILED",
        "PENDING",
        "PENDING",
    ]
    failed = progress["entities"][2]
    assert failed["response_id"] is None
    assert failed["failure"]["category"] == "PARTIAL_WRITE"
    assert "retry is safe" in failed["failure"]["safe_message"]
    recovered = client.post(f"/api/runs/{run['run_id']}/writeback")
    assert recovered.status_code == 200
    assert recovered.json()["stage"] == "VERIFIED"
    assert recovered.json()["reconciliation_verified"] is True
    assert len(recovered.json()["receipts"]) == 5
    recovered_progress = client.get(
        f"/api/runs/{run['run_id']}/writeback-progress"
    ).json()
    assert [entity["phase"] for entity in recovered_progress["entities"]] == [
        "VERIFIED"
    ] * 5
    assert len(apply_calls) == 6
    assert apply_calls[2] == apply_calls[3]
    listed = client.get("/api/runs")
    assert listed.status_code == 200
    assert [item["run_id"] for item in listed.json()] == [run["run_id"]]
