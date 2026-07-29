/**
 * Component-facing view models. Components import ONLY from here — never from
 * fixtures or from backend DTOs. The adapter layer (adapter/) maps raw backend
 * payloads into these shapes, so backend schema details never leak into the
 * component tree.
 *
 * Product-honesty is encoded in the types themselves:
 *  - `Disposition` has no "approved", "executed", "enforced" or "stopped" member.
 *  - `human_review` carries no proposed operational action.
 *  - `LifecyclePhase` separates proposed → recorded → verified; none means enacted.
 */

export type Disposition =
  | "allowed"
  | "remediate"
  | "stop_proposed"
  | "human_review"
  | "unaffected";

/** Dispositions that can appear as a terminal decision (never `unaffected`). */
export type DecisionDisposition = Exclude<Disposition, "unaffected">;

/**
 * Lifecycle of a proposed response. Deliberately excludes any "approved" /
 * "executed" / "enforced" state — the product proposes and records; it never enacts.
 */
export type LifecyclePhase = "proposed" | "recorded" | "verified";

export interface ChangeSummary {
  provider: string;
  obligationId: string;
  changeId?: string;
  fromVersion: string | number;
  toVersion: string | number;
  effectiveDate?: string;
  /** e.g. "Evidence SUPPORTED · 4 rules · 0 gaps" */
  reviewState: string;
}

export type ClauseEffect = "allowed" | "prohibited" | "review";
export interface Clause {
  /** verbatim citation, presented as-is */
  text: string;
  effect: ClauseEffect;
}

export interface GovernedSourceReference {
  displayName: string;
  nativeType: string;
  /** Omitted (undefined) when the backend does not expose a URN — never fabricated. */
  urn?: string;
  /** false before DataHub resolves the source; true after. */
  resolved: boolean;
  /** Honest pre-resolution label, e.g. "Source reference · pending DataHub resolution". */
  pendingLabel: string;
}

export interface LineageHop {
  name: string;
  assetType: string;
  urn?: string;
}

/**
 * One source→terminal path. Everything the graph and ledger need for a single
 * governed use. Geometry is NOT stored here — LineageStage computes lanes/paths
 * from the ordered terminal list.
 */
export interface TerminalPath {
  pathId: string;
  /** stable identity used by selectedTerminalId (decision id / slug). */
  id: string;
  responseIdentity: string;
  displayName: string;
  assetType: string;
  urn?: string;
  /** undefined → surfaces as "Owner unavailable" */
  owner?: string;
  usageClass: string;
  disposition: DecisionDisposition;
  /** the separate decision requirement, e.g. "Owner remediation decision required". */
  decisionRequirement: string;
  /** what the tool proposes (never what it did). */
  proposedAction: string;
  triggeringRule: string;
  explanation: string;
  /** intermediate hops between source and terminal (may be empty). */
  hops: LineageHop[];
  verificationState?: string;
  evidenceAvailable: boolean;
  datahubUrl?: string;
  recorded: boolean;
  readbackVerified: boolean;
}

export interface EvidenceField {
  k: string;
  v: string;
  mono?: boolean;
  italic?: boolean;
}

export interface EvidenceBundleVM {
  terminalId: string;
  terminalName: string;
  usage: string;
  available: boolean;
  /** decision-first: triggering clause, lineage path, proposed response. */
  primary: EvidenceField[];
  /** expandable: owner, raw rule id, native type, URN (if exposed), provenance. */
  secondary: EvidenceField[];
  datahubUrl?: string;
}

export interface UnaffectedControlVM {
  displayName: string;
  assetType: string;
  urn?: string;
  /** proof it sits outside the affected set. */
  note: string;
  /** Frame C: verified unmutated. */
  verified: boolean;
}

export interface TallyCounts {
  allowed: number;
  remediate: number;
  stopProposed: number;
  humanReview: number;
}

/** A ledger row derived from a TerminalPath + the current lifecycle phase. */
export interface ImpactPlanRowVM {
  id: string;
  index: number;
  displayName: string;
  assetType: string;
  owner?: string;
  disposition: DecisionDisposition;
  /** the standing decision requirement (constant across phases). */
  decisionRequirement: string;
  /** phase-derived marker: "Proposed · not recorded" → "recorded · readback verified ✓". */
  lifecycleMarker: string;
  /** human_review rows render the brass band + unresolved copy. */
  human: boolean;
  selected: boolean;
  /** verified check for the row (Frame C). */
  verified: boolean;
  responseIdentity: string;
  urn?: string;
  datahubUrl?: string;
}

/** Truthful runtime banner variants. */
export type BannerVariant =
  | "awaiting"
  | "empty"
  | "live"
  | "ok"
  | "err"
  | "unavailable";
