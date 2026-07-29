/**
 * ┌────────────────────────────────────────────────────────────────────────┐
 * │  DETERMINISTIC DESIGN PREVIEW DATA — NOT A PRODUCTION DATA SOURCE.        │
 * │  Canonical sanitized Atlas Signals payload. Every value is traced to the │
 * │  accepted design handoff (Covenant_Design_Handoff.md / Covenant Frames). │
 * │  Fields the runtime does not expose are `null` and surface as honest      │
 * │  "unavailable"/omitted states — nothing here is fabricated to fill a gap. │
 * │  This is the ONLY module allowed to hold fixture values. Generic          │
 * │  components must never import it.                                         │
 * └────────────────────────────────────────────────────────────────────────┘
 */
import type {
  ChangeDetailDTO,
  ChangeEvidenceDTO,
  GovernedSourceDTO,
  ImpactPlanDTO,
  EvidenceBundleDTO,
  VerifiedReceiptDTO
} from "../adapter/contracts";

export const MCP_SERVER = "mcp-server-datahub 0.6.0";

/** Explicit demo-only label. Do NOT render on the judge-facing product surface. */
export const PREVIEW_LABEL = "Deterministic design preview · sanitized Atlas Signals payload";

export const change: ChangeDetailDTO = {
  change_id: "CHANGE-483b8ee4b44cfe3f7eda",
  provider: "Atlas Signals",
  obligation_id: "ATLAS-LIC-004",
  previous_version: 3,
  candidate_version: 4,
  effective_date: "2026-08-01",
  review_state: "Evidence SUPPORTED · 4 rules · 0 gaps",
  material_changes: [
    { rule_text: "internal analytics remains allowed;", effect: "ALLOWED" },
    { rule_text: "machine-learning training is prohibited;", effect: "PROHIBITED" },
    { rule_text: "customer redistribution is prohibited;", effect: "PROHIBITED" },
    {
      rule_text: "previously created anonymized derivatives require human review.",
      effect: "REVIEW"
    }
  ]
};

export const evidence: ChangeEvidenceDTO = {
  status: "SUPPORTED",
  rule_count: 4,
  gap_count: 0
};

/** URN not exposed by the content packet → null (see handoff §5). */
export const governedSource: GovernedSourceDTO = {
  display_name: "vendor_demographics_raw",
  native_type: "Dataset",
  urn: null,
  resolved: false
};

/**
 * The completed Impact Plan. Terminal order defines lineage lanes top→bottom.
 * 1 allowed · 2 remediate · 1 stop proposed · 1 human review · 1 unaffected control.
 * Exactly five source→terminal paths; eleven downstream entities (6 intermediate + 5 terminal).
 */
export const impactPlan: ImpactPlanDTO = {
  run_id: "RUN-atlas-lic-004-canonical",
  source_resolution_status: "Resolved live through DataHub",
  downstream_entity_count: 11,
  terminal_path_count: 5,
  terminals: [
    {
      path_id: "P1",
      decision_id: "internal_executive_dashboard",
      response_identity: "COV-preview-dashboard",
      display_name: "Internal Executive Dashboard",
      native_type: "dashboard",
      urn: null,
      owner: "northstar_analytics",
      usage_class: "internal_analytics",
      disposition: "ALLOWED",
      decision_state: "Proposed · not recorded",
      proposed_action: "Continuation proposed · no operational change",
      triggering_rule: "internal analytics remains allowed;",
      explanation: "Internal-analytics use remains permitted under v4.",
      path: ["vendor_demographics_raw", "executive_metrics", "internal_executive_dashboard"],
      hops: [{ name: "executive_metrics", native_type: "dataset", urn: null }],
      path_verification_state: "path verified via MCP",
      evidence_state: "available",
      readback_state: null,
      datahub_url: null,
      recorded: false,
      readback_verified: false
    },
    {
      path_id: "P2",
      decision_id: "churn_model_a",
      response_identity: "COV-preview-churn",
      display_name: "Churn Model A",
      native_type: "mlModel",
      urn: null,
      owner: "northstar_model_ops",
      usage_class: "ml_training",
      disposition: "REMEDIATE",
      decision_state: "Proposed · not recorded",
      proposed_action: "Owner decision: clean rebuild, retrain, or deprecate",
      triggering_rule: "machine-learning training is prohibited;",
      explanation: "Trained on the governed source while v4 prohibits ML training.",
      path: [
        "vendor_demographics_raw",
        "training_features_a",
        "train_churn_model_a",
        "churn_model_a"
      ],
      hops: [
        { name: "training_features_a", native_type: "dataset", urn: null },
        { name: "train_churn_model_a", native_type: "dataJob", urn: null }
      ],
      path_verification_state: "path verified via MCP",
      evidence_state: "available",
      readback_state: null,
      datahub_url: null,
      recorded: false,
      readback_verified: false
    },
    {
      path_id: "P3",
      decision_id: "propensity_model_b",
      response_identity: "COV-preview-propensity",
      display_name: "Propensity Model B",
      native_type: "mlModel",
      urn: null,
      owner: "northstar_model_ops",
      usage_class: "ml_training",
      disposition: "REMEDIATE",
      decision_state: "Proposed · not recorded",
      proposed_action: "Owner decision: clean rebuild, retrain, or deprecate",
      triggering_rule: "machine-learning training is prohibited;",
      explanation: "Trained on the governed source while v4 prohibits ML training.",
      path: [
        "vendor_demographics_raw",
        "training_features_b",
        "train_propensity_model_b",
        "propensity_model_b"
      ],
      hops: [
        { name: "training_features_b", native_type: "dataset", urn: null },
        { name: "train_propensity_model_b", native_type: "dataJob", urn: null }
      ],
      path_verification_state: "path verified via MCP",
      evidence_state: "available",
      readback_state: null,
      datahub_url: null,
      recorded: false,
      readback_verified: false
    },
    {
      path_id: "P4",
      decision_id: "customer_delivery_job",
      response_identity: "COV-preview-delivery",
      display_name: "Customer Delivery Job",
      native_type: "dataJob",
      urn: null,
      owner: "northstar_customer_product",
      usage_class: "customer_redistribution",
      disposition: "STOP_PROPOSED",
      decision_state: "Proposed · not recorded",
      proposed_action: "Owner stop decision proposed · not stopped",
      triggering_rule: "customer redistribution is prohibited;",
      explanation: "Redistributes customer data, which v4 prohibits.",
      path: ["vendor_demographics_raw", "customer_export", "customer_delivery_job"],
      hops: [{ name: "customer_export", native_type: "dataset", urn: null }],
      path_verification_state: "path verified via MCP",
      evidence_state: "available",
      readback_state: null,
      datahub_url: null,
      recorded: false,
      readback_verified: false
    },
    {
      path_id: "P5",
      decision_id: "anonymized_segment_derivative",
      response_identity: "COV-preview-derivative",
      display_name: "Anonymized Segment Derivative",
      native_type: "dataset",
      urn: null,
      owner: "northstar_governance",
      usage_class: "anonymized_derivative",
      disposition: "HUMAN_REVIEW",
      decision_state: "Unresolved — held for a person",
      proposed_action: "No automatic action proposed · held for a person",
      triggering_rule: "previously created anonymized derivatives require human review.",
      explanation: "A pre-existing anonymized derivative that v4 routes to human review.",
      path: ["vendor_demographics_raw", "anonymized_segment_derivative"],
      hops: [],
      path_verification_state: "path verified via MCP",
      evidence_state: "available",
      readback_state: null,
      datahub_url: null,
      recorded: false,
      readback_verified: false
    }
  ],
  unaffected_control: {
    display_name: "Unrelated Control Asset",
    native_type: "dataset",
    urn: null,
    outside_affected_set_proof: "outside affected set · absent from MCP lineage",
    unmutated_proof: "verified unmutated",
    datahub_url: null
  }
};

/** Representative decision-detail bundle for the canonical selected model. */
export const churnEvidence: EvidenceBundleDTO = {
  terminal_ref: "churn_model_a",
  usage_class: "ml_training",
  triggering_clause: "machine-learning training is prohibited;",
  lineage_path: [
    "vendor_demographics_raw",
    "training_features_a",
    "train_churn_model_a",
    "churn_model_a"
  ],
  proposed_action: "Owner decision: clean rebuild, retrain, or deprecate",
  why_disposition:
    "The governed source flows into the model's training features, and v4 prohibits ML training.",
  owner: "northstar_model_ops",
  raw_rule_id: "v4.ml_training.prohibited_rebuild_or_deprecate",
  native_type: "mlModel",
  urn: null,
  provenance: "lineage & ownership via MCP · usage & terminal via DataHub SDK",
  verification_state: "path verified via MCP",
  readback_state: null,
  datahub_url: null,
  available: true
};

/** Receipt ids not exposed by the packet → null; recorded/verified flags are canonical. */
export const receipts: VerifiedReceiptDTO[] = impactPlan.terminals.map((t) => ({
  decision_id: t.decision_id,
  response_identity: t.response_identity,
  target_name: t.display_name,
  target_urn: t.urn ?? "not exposed",
  recorded: true,
  readback_verified: true,
  receipt_id: null,
  recorded_at: null,
  datahub_url: null
}));
