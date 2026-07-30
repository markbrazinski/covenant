from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlsplit

from datahub.metadata.schema_classes import GlobalTagsClass

from covenant.extraction import verify_and_submit_for_review
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
from src.reconciler.writeback import (
    PREFIX,
    apply,
    apply_one,
    proposed_action,
    readback,
    readback_mcp_one,
    readback_sdk_one,
)
from src.workflow.change_to_action import decision_context, reconcile, rejected_candidate
from src.workflow.impact import ImpactUnavailableError, analyse

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE_PATH = ROOT / "smoke-test" / "generated-state" / "gate3-api-state.json"
OLD_PATH = ROOT / "fixtures" / "atlas_license_v3.md"
NEW_PATH = ROOT / "fixtures" / "atlas_license_v4.md"


def datahub_entity_url(urn: str, entity_type: str) -> str | None:
    base_url = os.getenv("DATAHUB_UI_URL", "").strip().rstrip("/")
    if not base_url:
        return None
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    route = {
        "dataset": "dataset",
        "dashboard": "dashboard",
        "mlModel": "mlModels",
        "dataJob": "tasks",
    }.get(entity_type)
    if not route:
        return None
    return f"{base_url}/{route}/{quote(urn, safe=':,()')}/"


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


class _EntityWritebackFailure(RuntimeError):
    def __init__(self, category: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.category = category
        self.safe_message = safe_message


class CovenantService:
    def __init__(
        self,
        store: RunStore,
        *,
        impact_fn: Callable[[dict[str, Any]], dict[str, Any]] = analyse,
        apply_fn: Callable[..., dict[str, Any]] = apply,
        readback_fn: Callable[[list[dict[str, Any]]], dict[str, Any]] = readback,
        apply_one_fn: Callable[[dict[str, Any]], None] = apply_one,
        readback_mcp_one_fn: Callable[[dict[str, Any]], dict[str, Any]] = readback_mcp_one,
        readback_sdk_one_fn: Callable[[dict[str, Any]], dict[str, Any]] = readback_sdk_one,
    ) -> None:
        self.store = store
        self.impact_fn = impact_fn
        self.apply_fn = apply_fn
        self.readback_fn = readback_fn
        self.apply_one_fn = apply_one_fn
        self.readback_mcp_one_fn = readback_mcp_one_fn
        self.readback_sdk_one_fn = readback_sdk_one_fn

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

    def record_verified_extraction(
        self,
        candidate: dict[str, Any],
        documents: dict[str, Any],
        extraction_receipt: dict[str, Any],
        *,
        current_active_version: int,
        provider_name: str = "Atlas Signals",
    ) -> dict[str, Any]:
        """Verify a model extraction before recording any reviewable change."""
        verified_candidate, verification, transition = (
            verify_and_submit_for_review(
                candidate,
                documents,
                current_active_version=current_active_version,
            )
        )
        if verification["status"] != "PASS":
            return {
                "change_id": None,
                "provider_name": provider_name,
                "candidate": verified_candidate,
                "candidate_hash": None,
                "validation": {
                    "valid": False,
                    "errors": verification["failures"],
                    "candidate_delta_id": candidate.get("candidate_delta_id"),
                },
                "verification": verification,
                "extraction_receipt": extraction_receipt,
                "transitions": [],
                "persisted": False,
            }
        candidate_delta_id = candidate.get("candidate_delta_id")
        if not isinstance(candidate_delta_id, str) or not candidate_delta_id:
            raise APIStateError(
                "INVALID_EXTRACTED_CANDIDATE",
                "model extraction has no stable candidate identity",
                status_code=422,
            )
        extraction_metadata = candidate.get("extraction_metadata")
        metadata_keys = {
            "provider",
            "model_id",
            "prompt_version",
            "schema_version",
            "extraction_started_at",
            "extraction_completed_at",
            "input_token_count",
            "output_token_count",
        }
        receipt_matches = (
            isinstance(extraction_metadata, dict)
            and extraction_receipt.get("status") == "EXTRACTED_UNVERIFIED"
            and isinstance(extraction_receipt.get("attempts"), int)
            and extraction_receipt["attempts"] >= 1
            and all(
                extraction_receipt.get(key) == extraction_metadata.get(key)
                for key in metadata_keys
            )
        )
        if not receipt_matches:
            raise APIStateError(
                "INVALID_EXTRACTION_RECEIPT",
                "extraction receipt does not match the verified Bedrock candidate",
                status_code=422,
            )
        change_id = candidate_delta_id.replace("DELTA-", "CHANGE-", 1)
        normalized_documents: dict[str, str] = {}
        for ref, value in documents.items():
            if isinstance(value, str):
                normalized_documents[ref] = value
            elif isinstance(value, dict) and isinstance(value.get("text"), str):
                normalized_documents[ref] = value["text"]
            else:
                raise APIStateError(
                    "INVALID_SOURCE_DOCUMENT",
                    "source document has no verifiable text",
                    status_code=422,
                )
        document_hashes = {
            ref: sha256_text(text)
            for ref, text in normalized_documents.items()
        }
        existing = self.store.get_change(change_id)
        if existing:
            if existing.get("document_hashes") != document_hashes:
                raise APIStateError(
                    "IMMUTABLE_CHANGE_CONFLICT",
                    "stored change identity is bound to different source documents",
                )
            return existing
        record = {
            "change_id": change_id,
            "provider_name": provider_name,
            "candidate": verified_candidate,
            "candidate_hash": stable_json_hash(verified_candidate),
            "validation": {
                "valid": verification["status"] == "PASS",
                "errors": verification.get("failures", []),
                "candidate_delta_id": candidate_delta_id,
            },
            "verification": verification,
            "extraction_receipt": extraction_receipt,
            "transitions": [transition] if transition else [],
            "documents": normalized_documents,
            "document_hashes": document_hashes,
            "persisted": True,
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
        run["prior_verified_receipts"] = [
            item
            for item in previous_receipts
            if item.get("mcp_tag_readback_verified")
            and item.get("sdk_receipt_readback_verified")
        ]
        run["prior_receipt_readback"] = run.get("receipt_readback")
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
        decisions = self._ordered_decisions(run["impact"]["decisions"])
        prior_recorded_at = run.get("prior_recorded_at", {})
        preserved_receipts = [
            *run.get("receipts", []),
            *run.get("prior_verified_receipts", []),
        ]
        already_verified = {
            item["asset_urn"]
            for item in preserved_receipts
            if item.get("mcp_tag_readback_verified")
            and item.get("sdk_receipt_readback_verified")
        }
        incomplete_decisions = [
            decision
            for decision in decisions
            if decision["asset_urn"] not in already_verified
        ]
        run["writeback_events"] = []
        now = datetime.now(timezone.utc).isoformat()
        receipt_by_urn = {
            item["asset_urn"]: item for item in preserved_receipts
        }
        for index, decision in enumerate(decisions, start=1):
            prior_receipt = receipt_by_urn.get(decision["asset_urn"])
            if decision["asset_urn"] in already_verified:
                self._writeback_event(
                    run,
                    decision,
                    index,
                    "VERIFIED",
                    response_id=decision["decision_id"],
                    phase_started_at=prior_receipt.get("recorded_at") or now,
                )
            else:
                self._writeback_event(
                    run,
                    decision,
                    index,
                    "PENDING",
                    phase_started_at=now,
                )
        self._event(
            run,
            "WRITING",
            f"Recording {len(incomplete_decisions)} incomplete native DataHub proposal receipts; verified records are preserved",
            4,
            5,
        )
        self.store.put_run(run_id, run)
        states: list[dict[str, Any]] = []
        written = 0
        try:
            for index, decision in enumerate(decisions, start=1):
                if decision["asset_urn"] in already_verified:
                    state = self._state_from_existing_receipt(run, decision)
                    states.append(state)
                    continue
                response_id: str | None = None
                try:
                    self._writeback_event(run, decision, index, "WRITING")
                    self.store.put_run(run_id, run)
                    self.apply_one_fn(decision)
                    written += 1
                    response_id = decision["decision_id"]
                    self._writeback_event(
                        run,
                        decision,
                        index,
                        "WRITTEN",
                        response_id=response_id,
                    )
                    self.store.put_run(run_id, run)

                    self._writeback_event(
                        run,
                        decision,
                        index,
                        "VERIFYING_MCP",
                        response_id=response_id,
                    )
                    self.store.put_run(run_id, run)
                    mcp_state = self.readback_mcp_one_fn(decision)
                    if not mcp_state.get("mcp_tags_verified"):
                        raise _EntityWritebackFailure(
                            "READBACK_MISMATCH",
                            "DataHub MCP tag readback did not match the recorded proposal",
                        )
                    self._writeback_event(
                        run,
                        decision,
                        index,
                        "MCP_VERIFIED",
                        response_id=response_id,
                    )
                    self.store.put_run(run_id, run)

                    self._writeback_event(
                        run,
                        decision,
                        index,
                        "VERIFYING_SDK",
                        response_id=response_id,
                    )
                    self.store.put_run(run_id, run)
                    sdk_state = self.readback_sdk_one_fn(decision)
                    if not sdk_state.get("sdk_receipt_verified"):
                        raise _EntityWritebackFailure(
                            "READBACK_MISMATCH",
                            "DataHub SDK property readback did not match the recorded proposal",
                        )
                    self._writeback_event(
                        run,
                        decision,
                        index,
                        "SDK_VERIFIED",
                        response_id=response_id,
                    )
                    self.store.put_run(run_id, run)

                    states.append(
                        {
                            "asset_urn": decision["asset_urn"],
                            "entity_type": decision["entity_type"],
                            **mcp_state,
                            **sdk_state,
                        }
                    )
                    self._writeback_event(
                        run,
                        decision,
                        index,
                        "VERIFIED",
                        response_id=response_id,
                    )
                    self.store.put_run(run_id, run)
                except _EntityWritebackFailure:
                    raise
                except Exception as exc:
                    raise _EntityWritebackFailure(
                        "PARTIAL_WRITE",
                        "Native DataHub proposal write failed; retry is safe",
                    ) from exc
        except _EntityWritebackFailure as exc:
            failed_index, failed_decision = self._active_writeback_target(
                run, decisions
            )
            self._writeback_event(
                run,
                failed_decision,
                failed_index,
                "FAILED",
                response_id=(
                    failed_decision["decision_id"]
                    if self._latest_writeback_phase(
                        run, failed_decision["decision_id"]
                    )
                    not in {"PENDING", "WRITING"}
                    else None
                ),
                failure={
                    "category": exc.category,
                    "safe_message": exc.safe_message,
                },
            )
            try:
                partial_readback = self.readback_fn(decisions)
                run["receipts"] = self._receipts(
                    decisions, partial_readback, prior_recorded_at
                )
            except Exception:
                pass
            self._fail(
                run,
                exc.category,
                exc.safe_message,
                affected_set_produced=True,
            )
            self.store.put_run(run_id, run)
            raise APIStateError(
                exc.category,
                exc.safe_message,
                status_code=503,
                retryable=True,
                affected_set_produced=True,
            ) from exc
        write_result = {
            "mode": "write",
            "proposed": len(incomplete_decisions),
            "written": written,
            "verified": False,
        }
        receipt_readback = {
            "verified": len(states) == len(decisions)
            and all(
                state.get("mcp_tags_verified")
                and state.get("sdk_receipt_verified")
                for state in states
            ),
            "count": len(states),
            "states": states,
            "identity_set_verified": {
                state["asset_urn"] for state in states
            }
            == {decision["asset_urn"] for decision in decisions},
            "unexpected_urns": [],
            "read_interfaces": {
                "native_state": "DataHub MCP get_entities tags",
                "detailed_receipt": "DataHub SDK native property-aspect read",
            },
        }
        change = self._change(run["change_id"])
        reconciliation = reconcile(change["candidate"], decisions, receipt_readback)
        receipts = self._receipts(decisions, receipt_readback, prior_recorded_at)
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

    def writeback_progress(self, run_id: str) -> dict[str, Any]:
        run = self._run(run_id)
        events = run.get("writeback_events", [])
        latest: dict[str, dict[str, Any]] = {}
        for event in events:
            latest[event["entity_id"]] = event
        entities = sorted(
            latest.values(), key=lambda event: event["sequence_index"]
        )
        failed = any(
            event["phase"] == "FAILED" for event in entities
        )
        return {
            "run_id": run_id,
            "events": events,
            "entities": entities,
            "terminal": failed
            or (
                bool(entities)
                and all(
                    event["phase"] == "VERIFIED"
                    for event in entities
                )
            ),
            "failed": failed,
        }

    @staticmethod
    def _ordered_decisions(
        decisions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        disposition_order = {
            "allowed": 0,
            "remediate": 1,
            "stop_proposed": 2,
            "human_review": 3,
        }
        return sorted(
            decisions,
            key=lambda item: (
                disposition_order[item["proposed_disposition"]],
                item["lineage_paths"][0] if item["lineage_paths"] else [],
            ),
        )

    @staticmethod
    def _writeback_event(
        run: dict[str, Any],
        decision: dict[str, Any],
        sequence_index: int,
        phase: str,
        *,
        response_id: str | None = None,
        failure: dict[str, str] | None = None,
        phase_started_at: str | None = None,
    ) -> None:
        run.setdefault("writeback_events", []).append(
            {
                "run_id": run["run_id"],
                "entity_id": decision["decision_id"],
                "terminal_display_name": decision["asset_name"],
                "sequence_index": sequence_index,
                "phase": phase,
                "phase_started_at": phase_started_at
                or datetime.now(timezone.utc).isoformat(),
                "response_id": response_id,
                "failure": failure,
            }
        )

    @staticmethod
    def _latest_writeback_phase(
        run: dict[str, Any], entity_id: str
    ) -> str | None:
        for event in reversed(run.get("writeback_events", [])):
            if event["entity_id"] == entity_id:
                return event["phase"]
        return None

    def _active_writeback_target(
        self,
        run: dict[str, Any],
        decisions: list[dict[str, Any]],
    ) -> tuple[int, dict[str, Any]]:
        for index, decision in enumerate(decisions, start=1):
            phase = self._latest_writeback_phase(
                run, decision["decision_id"]
            )
            if phase not in {"PENDING", "VERIFIED", "FAILED"}:
                return index, decision
        for index, decision in enumerate(decisions, start=1):
            if (
                self._latest_writeback_phase(run, decision["decision_id"])
                == "PENDING"
            ):
                return index, decision
        raise RuntimeError("writeback failure had no active entity")

    def _state_from_existing_receipt(
        self,
        run: dict[str, Any],
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        prior = next(
            (
                item
                for item in (
                    run.get("receipt_readback")
                    or run.get("prior_receipt_readback")
                    or {}
                ).get("states", [])
                if item.get("asset_urn") == decision["asset_urn"]
                and item.get("mcp_tags_verified")
                and item.get("sdk_receipt_verified")
            ),
            None,
        )
        if prior is not None:
            return prior
        return {
            "asset_urn": decision["asset_urn"],
            "entity_type": decision["entity_type"],
            **self.readback_mcp_one_fn(decision),
            **self.readback_sdk_one_fn(decision),
        }

    @staticmethod
    def _receipts(
        decisions: list[dict[str, Any]],
        receipt_readback: dict[str, Any],
        prior_recorded_at: dict[str, str | None],
    ) -> list[dict[str, Any]]:
        state_by_urn = {
            item["asset_urn"]: item for item in receipt_readback.get("states", [])
        }
        receipts = []
        for decision in decisions:
            urn = decision["asset_urn"]
            state = state_by_urn.get(urn, {})
            recorded_at = state.get(PREFIX + "recorded_at")
            tags = graph().get_aspect(urn, GlobalTagsClass)
            tag_values = [item.tag for item in (tags.tags if tags else [])]
            written = bool(state.get("sdk_receipt_verified"))
            receipts.append(
                {
                    "decision_id": decision["decision_id"],
                    "asset_urn": urn,
                    "written": written,
                    "mcp_tag_readback_verified": bool(
                        state.get("mcp_tags_verified")
                    ),
                    "sdk_receipt_readback_verified": bool(
                        state.get("sdk_receipt_verified")
                    ),
                    "stable_recorded_at": bool(recorded_at)
                    and prior_recorded_at.get(urn, recorded_at) == recorded_at,
                    "duplicate_tags": len(tag_values) != len(set(tag_values)),
                    "recorded_at": recorded_at,
                    "datahub_url": datahub_entity_url(
                        urn, decision["entity_type"]
                    ),
                }
            )
        return receipts

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
        disposition_order = {
            "allowed": 0,
            "remediate": 1,
            "stop_proposed": 2,
            "human_review": 3,
        }
        projected_decisions = sorted(
            (impact or {}).get("decisions", []),
            key=lambda item: (
                disposition_order[item["proposed_disposition"]],
                item["lineage_paths"][0] if item["lineage_paths"] else [],
            ),
        )
        for path_index, decision in enumerate(projected_decisions, start=1):
            decisions.append(
                {
                    "path_id": f"P{path_index}",
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
                    "path_nodes": decision.get("lineage_path_nodes", []),
                    "triggering_rule": rules.get(decision["usage_class"], {}),
                    "controlling_policy_rule": decision[
                        "controlling_policy_rule"
                    ],
                    "confidence_meaning": decision["confidence_meaning"],
                    "actor_class": decision["actor_class"],
                    "metadata_interfaces": decision["metadata_interfaces"],
                    "mcp_path_verified": bool(decision["lineage_paths"]),
                    "readback_verified": bool(
                        (run.get("reconciliation") or {}).get("verified", False)
                    ),
                    "datahub_url": datahub_entity_url(
                        decision["asset_urn"], decision["entity_type"]
                    ),
                }
            )
        event = run["events"][-1]
        unaffected = (impact or {}).get("unaffected", [])
        unaffected_control = None
        if unaffected:
            control = unaffected[0]
            unaffected_control = {
                "asset_urn": control["asset_urn"],
                "display_name": control["asset_name"],
                "native_type": "dataset",
                "outside_affected_set_proof": control["reason"],
                "unmutated_verified": bool(
                    (run.get("reconciliation") or {}).get(
                        "unrelated_control_isolated", False
                    )
                ),
                "datahub_url": datahub_entity_url(
                    control["asset_urn"], "dataset"
                ),
            }
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
            "source": (impact or {}).get("source"),
            "graph": (impact or {}).get("graph"),
            "counts": (impact or {}).get("counts"),
            "decisions": decisions,
            "receipts": run.get("receipts", []),
            "reconciliation_verified": bool(
                (run.get("reconciliation") or {}).get("verified", False)
            ),
            "unaffected_control": unaffected_control,
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
