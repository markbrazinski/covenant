from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SourceAsset(BaseModel):
    urn: str
    display_name: str
    native_type: str = "Dataset"


class ChangeSummary(BaseModel):
    change_id: str
    obligation_id: str | None
    provider_name: str
    superseded_version: int | None
    candidate_version: int | None
    effective_at: str | None
    source_asset: SourceAsset
    lifecycle_state: str
    evidence_state: str
    material_rule_count: int
    unresolved_gap_count: int
    candidate_hash: str


class AnalyzeRequest(BaseModel):
    fixture_id: Literal["atlas_v3_v4"] | None = "atlas_v3_v4"
    old_text: str | None = Field(default=None, max_length=100_000)
    new_text: str | None = Field(default=None, max_length=100_000)

    @model_validator(mode="after")
    def select_one_input_mode(self) -> "AnalyzeRequest":
        supplied = self.old_text is not None or self.new_text is not None
        if supplied and (self.old_text is None or self.new_text is None):
            raise ValueError("old_text and new_text must be supplied together")
        if supplied:
            self.fixture_id = None
        elif self.fixture_id is None:
            raise ValueError("select atlas_v3_v4 or supply both document texts")
        return self


class ActivationRequest(BaseModel):
    reviewed_candidate_hash: str = Field(min_length=64, max_length=64)
    label: str
    actor: str = Field(pattern=r"^synthetic_[a-z0-9_]+$")
    review_note: str = Field(min_length=1, max_length=500)


class PathNode(BaseModel):
    urn: str
    display_name: str
    native_type: str


class ImpactTerminal(BaseModel):
    path_id: str
    decision_id: str
    asset_urn: str
    display_name: str
    native_type: str
    owner: str | None
    usage_class: str | None
    disposition: str
    decision_state: str
    proposed_action: str
    paths: list[list[str]]
    path_nodes: list[list[PathNode]]
    triggering_rule: dict[str, Any]
    controlling_policy_rule: str
    confidence_meaning: str
    actor_class: str
    metadata_interfaces: dict[str, str]
    mcp_path_verified: bool
    readback_verified: bool = False
    datahub_url: str | None = None


class ResolvedSource(BaseModel):
    urn: str
    resolved_via: str
    obligation_id: str
    active_version: int


class GraphProjection(BaseModel):
    downstream_entity_count: int
    terminal_count: int
    read_interface: str


class UnaffectedControl(BaseModel):
    asset_urn: str
    display_name: str
    native_type: str
    outside_affected_set_proof: str
    unmutated_verified: bool
    datahub_url: str | None = None


class RunProgress(BaseModel):
    run_id: str
    stage: str
    message: str
    completed: int
    total: int
    error: dict[str, Any] | None = None


class VerifiedReceipt(BaseModel):
    decision_id: str
    asset_urn: str
    written: bool
    mcp_tag_readback_verified: bool
    sdk_receipt_readback_verified: bool
    stable_recorded_at: bool
    duplicate_tags: bool
    recorded_at: str | None
    datahub_url: str | None = None


WritebackPhase = Literal[
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


class WritebackFailure(BaseModel):
    category: Literal["PARTIAL_WRITE", "READBACK_MISMATCH"]
    safe_message: str


class WritebackEntityEvent(BaseModel):
    run_id: str
    entity_id: str
    terminal_display_name: str
    sequence_index: int = Field(ge=1)
    phase: WritebackPhase
    phase_started_at: datetime
    response_id: str | None = None
    failure: WritebackFailure | None = None

    @model_validator(mode="after")
    def validate_phase_payload(self) -> "WritebackEntityEvent":
        if self.phase == "FAILED" and self.failure is None:
            raise ValueError("FAILED events require a safe failure projection")
        if self.phase != "FAILED" and self.failure is not None:
            raise ValueError("failure is present only for FAILED events")
        if self.phase in {
            "WRITTEN",
            "VERIFYING_MCP",
            "MCP_VERIFIED",
            "VERIFYING_SDK",
            "SDK_VERIFIED",
            "VERIFIED",
        } and self.response_id is None:
            raise ValueError(f"{self.phase} events require a response_id")
        return self


class WritebackProgress(BaseModel):
    run_id: str
    events: list[WritebackEntityEvent] = Field(default_factory=list)
    entities: list[WritebackEntityEvent] = Field(default_factory=list)
    terminal: bool
    failed: bool


class RunDetail(BaseModel):
    run_id: str
    change_id: str
    activation_id: str
    stage: str
    progress: RunProgress
    source: ResolvedSource | None = None
    graph: GraphProjection | None = None
    counts: dict[str, int] | None = None
    decisions: list[ImpactTerminal] = Field(default_factory=list)
    receipts: list[VerifiedReceipt] = Field(default_factory=list)
    reconciliation_verified: bool = False
    unaffected_control: UnaffectedControl | None = None


class ErrorProjection(BaseModel):
    code: str
    message: str
    affected_set_produced: bool | None = None
    retryable: bool
