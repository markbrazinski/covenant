from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from datahub.metadata.schema_classes import GlobalTagsClass

from src.api.schemas import AnalyzeRequest
from src.api.store import RunStore
from src.datahub_client.core import entity_urn, graph
from src.obligations.candidate import (
    SYNTHETIC_APPROVAL_LABEL,
    activate_synthetic_test,
    active_candidate_policy,
    extract_candidate_text,
    sha256_text,
    stable_json_hash,
    submit_for_review,
    validate_candidate,
)
from src.reconciler.writeback import apply, proposed_action, readback
from src.workflow.change_to_action import decision_context, reconcile, rejected_candidate
from src.workflow.impact import ImpactUnavailableError, analyse

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE_PATH = ROOT / "smoke-test" / "generated-state" / "gate3-api-state.json"
OLD_PATH = ROOT / "fixtures" / "atlas_license_v3.md"
NEW_PATH = ROOT / "fixtures" / "atlas_license_v4.md"


class APIStateError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 409,
        retryable: bool = False,
        affected_set_produced: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable
        self.affected_set_produced = affected_set_produced


class CovenantService:
    def __init__(
        self,
        store: RunStore,
        *,
        impact_fn: Callable[[dict[str, Any]], dict[str, Any]] = analyse,
        apply_fn: Callable[..., dict[str, Any]] = apply,
        readback_fn: Callable[[list[dict[str, Any]]], dict[str, Any]] = readback,
    ) -> None:
        self.store = store
        self.impact_fn = impact_fn
        self.apply_fn = apply_fn
        self.readback_fn = readback_fn

    def ensure_canonical_change(self) -> dict[str, Any]:
        return self.analyze_change(AnalyzeRequest())

    def analyze_change(self, request: AnalyzeRequest) -> dict[str, Any]:
        if request.old_text is not None and request.new_text is not None:
            old_text, new_text = request.old_text, request.new_text
            old_ref, new_ref = "api-upload:version-3", "api-upload:version-4"
        else:
            old_text, new_text = OLD_PATH.read_text(), NEW_PATH.read_text()
            old_ref = "fixtures/atlas_license_v3.md"
            new_ref = "fixtures/atlas_license_v4.md"
        candidate = extract_candidate_text(
            old_text, new_text, old_ref=old_ref, new_ref=new_ref
        )
        change_id = candidate["candidate_delta_id"].replace("DELTA-", "CHANGE-", 1)
        existing = self.store.get_change(change_id)
        if existing:
            return existing
        documents = {old_ref: old_text, new_ref: new_text}
        validation = validate_candidate(candidate, documents, current_active_version=3)
        transitions: list[dict[str, Any]] = []
        if not validation["valid"]:
            candidate = rejected_candidate(
                candidate, validation, "deterministic evidence validation failed"
            )
        elif not candidate["material_change"]:
            candidate = rejected_candidate(
                candidate, validation, "no material obligation change"
            )
        else:
            candidate, transition = submit_for_review(candidate, validation)
            transitions.append(transition)
        candidate_hash = stable_json_hash(candidate)
        record = {
            "change_id": change_id,
            "provider_name": "Atlas Signals",
            "candidate": candidate,
            "candidate_hash": candidate_hash,
            "validation": validation,
            "transitions": transitions,
            "documents": documents,
            "document_hashes": {
                old_ref: sha256_text(old_text),
                new_ref: sha256_text(new_text),
            },
        }
        self.store.put_change(change_id, record)
        return record

    def change_summary(self, record: dict[str, Any]) -> dict[str, Any]:
        candidate = record["candidate"]
        return {
            "change_id": record["change_id"],
            "obligation_id": candidate["obligation_id"],
            "provider_name": record["provider_name"],
            "superseded_version": candidate["supersedes_version"],
            "candidate_version": candidate["candidate_version"],
            "effective_at": candidate["effective_at"],
            "source_asset": {
                "urn": entity_urn("vendor_demographics_raw"),
                "display_name": "vendor_demographics_raw",
                "native_type": "Dataset",
            },
            "lifecycle_state": candidate["lifecycle_state"],
            "evidence_state": candidate["evidence_status"],
            "material_rule_count": len(candidate["rules"]),
            "unresolved_gap_count": len(candidate["unresolved_gaps"]),
            "candidate_hash": record["candidate_hash"],
        }

    def list_changes(self) -> list[dict[str, Any]]:
        return [
            self.change_summary(record)
            for record in self.store.snapshot()["changes"].values()
        ]

    def activate(
        self,
        change_id: str,
        *,
        reviewed_candidate_hash: str,
        label: str,
        actor: str,
        review_note: str,
    ) -> dict[str, Any]:
        record = self._change(change_id)
        candidate = record["candidate"]
        if reviewed_candidate_hash != record["candidate_hash"]:
            raise APIStateError(
                "CANDIDATE_HASH_MISMATCH",
                "reviewed candidate hash does not match the current evidence-bound candidate",
            )
        if label != SYNTHETIC_APPROVAL_LABEL:
            raise APIStateError(
                "ACTIVATION_REFUSED",
                "activation requires the literal SYNTHETIC TEST APPROVAL label",
            )
        if candidate["lifecycle_state"] == "ACTIVE":
            activation = candidate["activation"]
            if actor != activation["actor"]:
                raise APIStateError(
                    "ACTIVATION_CONFLICT",
                    "active candidate is already bound to a different synthetic actor",
                )
        else:
            try:
                candidate, activation = activate_synthetic_test(
                    candidate,
                    label=label,
                    actor=actor,
                    rationale=review_note,
                )
            except ValueError as exc:
                raise APIStateError("ACTIVATION_REFUSED", str(exc)) from exc
            record["candidate"] = candidate
            record["transitions"].append(activation)
            self.store.put_change(change_id, record)
        run_id = activation["activation_id"].replace("ACTIVATION-", "RUN-", 1)
        run = self.store.get_run(run_id)
        if run:
            return run
        run = {
            "run_id": run_id,
            "change_id": change_id,
            "activation_id": activation["activation_id"],
            "stage": "ACTIVE",
            "events": [],
            "impact": None,
            "receipts": [],
            "reconciliation": None,
        }
        self._event(
            run,
            "ACTIVE",
            "Reviewed candidate activated for impact analysis",
            0,
            5,
        )
        self.store.put_run(run_id, run)
        return run

    def run_impact(self, run_id: str) -> dict[str, Any]:
        run = self._run(run_id)
        change = self._change(run["change_id"])
        candidate = change["candidate"]
        if candidate["lifecycle_state"] != "ACTIVE":
            raise APIStateError(
                "ACTIVATION_REQUIRED", "impact analysis requires an ACTIVE reviewed candidate"
            )
        previous_receipts = run.get("receipts", [])
        run["prior_recorded_at"] = {
            item["asset_urn"]: item.get("recorded_at") for item in previous_receipts
        }
        run["impact"] = None
        run["writeback"] = None
        run["receipt_readback"] = None
        run["receipts"] = []
        run["reconciliation"] = None
        self._event(
            run,
            "RESOLVING_IMPACT",
            "Resolving source and tracing downstream lineage through DataHub MCP",
            1,
            5,
        )
        self.store.put_run(run_id, run)
        try:
            report = self.impact_fn(active_candidate_policy(candidate))
        except ImpactUnavailableError as exc:
            self._fail(
                run,
                "IMPACT_UNAVAILABLE",
                str(exc),
                affected_set_produced=False,
            )
            self.store.put_run(run_id, run)
            raise APIStateError(
                "IMPACT_UNAVAILABLE",
                str(exc),
                status_code=503,
                retryable=True,
                affected_set_produced=False,
            ) from exc
        except Exception as exc:
            self._fail(
                run,
                "DATAHUB_UNAVAILABLE",
                "DataHub impact analysis failed; no downstream plan was accepted",
                affected_set_produced=False,
            )
            self.store.put_run(run_id, run)
            raise APIStateError(
                "DATAHUB_UNAVAILABLE",
                "DataHub impact analysis failed; no downstream plan was accepted",
                status_code=503,
                retryable=True,
                affected_set_produced=False,
            ) from exc
        context = decision_context(candidate)
        for decision in report["decisions"]:
            decision["gate2_context"] = context
        run["impact"] = report
        self._event(run, "IMPACT_READY", "Five graph-derived responses are ready", 3, 5)
        self.store.put_run(run_id, run)
        return run

    def writeback(self, run_id: str) -> dict[str, Any]:
        run = self._run(run_id)
        if not run.get("impact"):
            raise APIStateError(
                "IMPACT_REQUIRED", "writeback requires a successful graph-derived impact plan"
            )
        decisions = run["impact"]["decisions"]
        prior_recorded_at = run.get("prior_recorded_at", {})
        self._event(run, "WRITING", "Writing five native DataHub decision receipts", 4, 5)
        self.store.put_run(run_id, run)
        try:
            write_result = self.apply_fn(decisions)
            receipt_readback = self.readback_fn(decisions)
        except Exception as exc:
            self._fail(
                run,
                "PARTIAL_WRITE",
                "Writeback did not reconcile; retry is safe and preserves stable identity",
                affected_set_produced=True,
            )
            self.store.put_run(run_id, run)
            raise APIStateError(
                "PARTIAL_WRITE",
                "Writeback did not reconcile; retry is safe and preserves stable identity",
                status_code=503,
                retryable=True,
                affected_set_produced=True,
            ) from exc
        change = self._change(run["change_id"])
        reconciliation = reconcile(change["candidate"], decisions, receipt_readback)
        state_by_urn = {item["asset_urn"]: item for item in receipt_readback["states"]}
        receipts = []
        for decision in decisions:
            urn = decision["asset_urn"]
            state = state_by_urn[urn]
            recorded_at = state.get("covenant.decision.recorded_at")
            tags = graph().get_aspect(urn, GlobalTagsClass)
            tag_values = [item.tag for item in (tags.tags if tags else [])]
            receipts.append(
                {
                    "decision_id": decision["decision_id"],
                    "asset_urn": urn,
                    "written": True,
                    "mcp_tag_readback_verified": state["mcp_tags_verified"],
                    "sdk_receipt_readback_verified": state["sdk_receipt_verified"],
                    "stable_recorded_at": prior_recorded_at.get(urn, recorded_at)
                    == recorded_at,
                    "duplicate_tags": len(tag_values) != len(set(tag_values)),
                    "recorded_at": recorded_at,
                }
            )
        run.update(
            writeback=write_result,
            receipt_readback=receipt_readback,
            receipts=receipts,
            reconciliation=reconciliation,
        )
        if not reconciliation["verified"]:
            self._fail(
                run,
                "READBACK_MISMATCH",
                "DataHub receipt readback did not reconcile",
                affected_set_produced=True,
            )
            self.store.put_run(run_id, run)
            raise APIStateError(
                "READBACK_MISMATCH",
                "DataHub receipt readback did not reconcile",
                status_code=503,
                retryable=True,
                affected_set_produced=True,
            )
        self._event(run, "VERIFIED", "Five decisions written and five verified", 5, 5)
        self.store.put_run(run_id, run)
        return run

    def replay(self, run_id: str) -> dict[str, Any]:
        self.run_impact(run_id)
        return self.writeback(run_id)

    def run_detail(self, run: dict[str, Any]) -> dict[str, Any]:
        impact = run.get("impact")
        change = self._change(run["change_id"])
        rules = {
            rule["usage_class"]: rule for rule in change["candidate"].get("rules", [])
        }
        decisions = []
        for decision in (impact or {}).get("decisions", []):
            decisions.append(
                {
                    "decision_id": decision["decision_id"],
                    "asset_urn": decision["asset_urn"],
                    "display_name": decision["asset_name"],
                    "native_type": decision["entity_type"],
                    "owner": decision["decision_owner"],
                    "usage_class": decision["usage_class"],
                    "disposition": decision["proposed_disposition"].upper(),
                    "decision_state": decision["decision_state"].upper(),
                    "proposed_action": proposed_action(decision["proposed_disposition"]),
                    "paths": decision["lineage_paths"],
                    "triggering_rule": rules.get(decision["usage_class"], {}),
                    "mcp_path_verified": bool(decision["lineage_paths"]),
                    "readback_verified": bool(
                        (run.get("reconciliation") or {}).get("verified", False)
                    ),
                }
            )
        event = run["events"][-1]
        return {
            "run_id": run["run_id"],
            "change_id": run["change_id"],
            "activation_id": run["activation_id"],
            "stage": run["stage"],
            "progress": {
                "run_id": run["run_id"],
                "stage": event["stage"],
                "message": event["message"],
                "completed": event["completed"],
                "total": event["total"],
                "error": run.get("error"),
            },
            "counts": (impact or {}).get("counts"),
            "decisions": decisions,
            "receipts": run.get("receipts", []),
            "reconciliation_verified": bool(
                (run.get("reconciliation") or {}).get("verified", False)
            ),
        }

    def _change(self, change_id: str) -> dict[str, Any]:
        record = self.store.get_change(change_id)
        if not record:
            raise APIStateError("CHANGE_NOT_FOUND", "change was not found", status_code=404)
        return record

    def _run(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        if not run:
            raise APIStateError("RUN_NOT_FOUND", "run was not found", status_code=404)
        return run

    @staticmethod
    def _event(
        run: dict[str, Any], stage: str, message: str, completed: int, total: int
    ) -> None:
        run.pop("error", None)
        run["stage"] = stage
        run["events"].append(
            {
                "sequence": len(run["events"]) + 1,
                "stage": stage,
                "message": message,
                "completed": completed,
                "total": total,
            }
        )

    @staticmethod
    def _fail(
        run: dict[str, Any],
        code: str,
        message: str,
        *,
        affected_set_produced: bool,
    ) -> None:
        run["stage"] = code
        run["error"] = {
            "code": code,
            "message": message,
            "affected_set_produced": affected_set_produced,
            "retryable": True,
        }
        run["events"].append(
            {
                "sequence": len(run["events"]) + 1,
                "stage": code,
                "message": message,
                "completed": 0,
                "total": 5,
            }
        )
