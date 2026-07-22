from __future__ import annotations

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


class ImpactTerminal(BaseModel):
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
    triggering_rule: dict[str, Any]
    mcp_path_verified: bool
    readback_verified: bool = False


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
    recorded_at: str


class RunDetail(BaseModel):
    run_id: str
    change_id: str
    activation_id: str
    stage: str
    progress: RunProgress
    counts: dict[str, int] | None = None
    decisions: list[ImpactTerminal] = Field(default_factory=list)
    receipts: list[VerifiedReceipt] = Field(default_factory=list)
    reconciliation_verified: bool = False


class ErrorProjection(BaseModel):
    code: str
    message: str
    affected_set_produced: bool | None = None
    retryable: bool
