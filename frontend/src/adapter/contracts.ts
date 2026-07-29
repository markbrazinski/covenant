/**
 * BACKEND-FACING DATA TRANSFER OBJECTS (sample interfaces).
 *
 * These express the *frontend's needs* from the Covenant Gate 3 API without
 * guessing HTTP paths or transport. The repository agent implements a real
 * adapter that returns these shapes; the view-model mappers in data/viewModels.ts
 * translate them into the component-facing types in types/domain.ts.
 *
 * Any field the runtime does not expose is `null` (mapped to an honest
 * "unavailable" / omitted presentation) — never fabricated.
 */

export type Nullable<T> = T | null;

export interface ChangeDetailDTO {
  change_id: Nullable<string>;
  provider: string;
  obligation_id: string;
  previous_version: string | number;
  candidate_version: string | number;
  effective_date: Nullable<string>;
  review_state: string;
  material_changes: Array<{
    rule_text: string;
    /** "ALLOWED" | "PROHIBITED" | "REVIEW" */
    effect: string;
  }>;
}

export interface ChangeEvidenceDTO {
  /** e.g. "SUPPORTED", plus rule/gap counts */
  status: string;
  rule_count: number;
  gap_count: number;
}

export interface GovernedSourceDTO {
  display_name: string;
  native_type: string;
  urn: Nullable<string>;
  /** false before impact analysis resolves the source through DataHub */
  resolved: boolean;
}

export interface ActivationAck {
  /** identifier for the analysis run the activation authorized */
  run_id: string;
  authorized: true;
}

/** Emitted repeatedly while an analysis run progresses. */
export interface RunProgressDTO {
  run_id: string;
  /** Coarse UI phase. Real mode maps only API-observed work, then completion. */
  phase: "resolving_impact" | "complete";
  /** Exact current API stage and message; never inferred from presentation timers. */
  server_stage: string;
  server_message: string;
  source_resolution_status: string;
  /** downstream entities discovered so far (may be null until known) */
  downstream_entity_count: Nullable<number>;
  /** total terminal paths the run will yield */
  terminal_path_count: Nullable<number>;
  /** Completed-result presentation geometry; always zero before IMPACT_READY. */
  tiers_resolved: number;
  tiers_total: number;
  /** terminals produced so far — never populated before the run derives them */
  terminals_revealed: number;
}

export interface TerminalDecisionDTO {
  path_id: string;
  decision_id: string;
  response_identity: string;
  display_name: string;
  native_type: string;
  urn: Nullable<string>;
  owner: Nullable<string>;
  usage_class: string;
  /** "ALLOWED" | "REMEDIATE" | "STOP_PROPOSED" | "HUMAN_REVIEW" */
  disposition: string;
  decision_state: string;
  proposed_action: string;
  triggering_rule: string;
  explanation: string;
  /** ordered display names, governed source → terminal */
  path: string[];
  /** ordered intermediate hops (name + native type + urn) */
  hops: Array<{ name: string; native_type: string; urn: Nullable<string> }>;
  path_verification_state: Nullable<string>;
  evidence_state: string;
  readback_state: Nullable<string>;
  datahub_url: Nullable<string>;
  recorded: boolean;
  readback_verified: boolean;
}

export interface UnaffectedControlDTO {
  display_name: string;
  native_type: string;
  urn: Nullable<string>;
  outside_affected_set_proof: string;
  unmutated_proof: Nullable<string>;
  datahub_url: Nullable<string>;
}

export interface ImpactPlanDTO {
  run_id: string;
  source_resolution_status: string;
  downstream_entity_count: Nullable<number>;
  terminal_path_count: number;
  terminals: TerminalDecisionDTO[];
  unaffected_control: Nullable<UnaffectedControlDTO>;
}

export interface EvidenceBundleDTO {
  terminal_ref: string;
  usage_class: string;
  triggering_clause: string;
  lineage_path: string[];
  proposed_action: string;
  why_disposition: string;
  owner: Nullable<string>;
  raw_rule_id: string;
  native_type: string;
  urn: Nullable<string>;
  provenance: string;
  verification_state: Nullable<string>;
  readback_state: Nullable<string>;
  datahub_url: Nullable<string>;
  /** false → render "Evidence unavailable"; do not substitute placeholders */
  available: boolean;
}

/** Emitted repeatedly while proposed responses are recorded + read back. */
export interface RecordingProgressDTO {
  run_id: string;
  phase: "recording" | "verifying_readbacks" | "reconciled" | "partial";
  target_count: number;
  recorded_count: number;
  readback_verified_count: number;
  /** decision ids recorded so far */
  recorded_ids: string[];
  /** decision ids whose readback is verified so far */
  verified_ids: string[];
  /** decision ids still incomplete (partial-write visibility) */
  incomplete_ids: string[];
  stable_replay: boolean;
}

export interface VerifiedReceiptDTO {
  decision_id: string;
  response_identity: string;
  target_name: string;
  target_urn: string;
  recorded: boolean;
  readback_verified: boolean;
  /** MCP tag / SDK receipt id, if exposed */
  receipt_id: Nullable<string>;
  recorded_at: Nullable<string>;
  datahub_url: Nullable<string>;
}

export interface RecordedPlanDTO {
  run_id: string;
  change_id: string;
  recorded_at: Nullable<string>;
  plan: ImpactPlanDTO;
  receipts: VerifiedReceiptDTO[];
}

export interface ErrorProjectionDTO {
  /** "DATAHUB_UNAVAILABLE" | "EVIDENCE_UNAVAILABLE" | "PARTIAL_WRITE" | … */
  code: string;
  title: string;
  detail: string;
  /** always true for DataHub/MCP failure — the affected set is cleared */
  clears_affected_set: boolean;
}
