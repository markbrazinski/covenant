/**
 * DTO → view-model mappers. This is the only place that knows the backend field
 * names. Components consume the returned domain types (types/domain.ts) and never
 * see a DTO. Enum casing, owner/URN fallbacks, and lifecycle language live here.
 */
import type {
  ChangeDetailDTO,
  ChangeEvidenceDTO,
  GovernedSourceDTO,
  ImpactPlanDTO,
  TerminalDecisionDTO,
  EvidenceBundleDTO,
  UnaffectedControlDTO,
  WritebackEntityProgressDTO
} from "../adapter/contracts";
import type {
  ChangeSummary,
  Clause,
  ClauseEffect,
  GovernedSourceReference,
  TerminalPath,
  DecisionDisposition,
  EvidenceBundleVM,
  UnaffectedControlVM,
  TallyCounts,
  ImpactPlanRowVM,
  LifecyclePhase
} from "../types/domain";

export function dispositionFromDTO(s: string): DecisionDisposition {
  switch (s.toUpperCase()) {
    case "ALLOWED":
      return "allowed";
    case "REMEDIATE":
      return "remediate";
    case "STOP_PROPOSED":
      return "stop_proposed";
    case "HUMAN_REVIEW":
      return "human_review";
    default:
      return "allowed";
  }
}

function clauseEffectFromDTO(s: string): ClauseEffect {
  switch (s.toUpperCase()) {
    case "PROHIBITED":
      return "prohibited";
    case "REVIEW":
      return "review";
    default:
      return "allowed";
  }
}

/** Display-cased disposition label. */
export const DISPOSITION_LABEL: Record<DecisionDisposition, string> = {
  allowed: "Allowed",
  remediate: "Remediate",
  stop_proposed: "Stop proposed",
  human_review: "Human review"
};

/**
 * The standing decision requirement per disposition (locked spec copy). This is
 * what still needs a human — it never says a response was taken.
 */
export const DECISION_REQUIREMENT: Record<DecisionDisposition, string> = {
  allowed: "Continuation proposed",
  remediate: "Owner remediation decision required",
  stop_proposed: "Owner stop decision required · not stopped",
  human_review: "Human review required · no automatic action proposed"
};

/**
 * Phase-derived lifecycle marker. Proposed ≠ approved; Recorded ≠ executed;
 * Verified ≠ enforced. Human review stays unresolved; stop stays not-stopped.
 */
export function lifecycleMarker(
  disposition: DecisionDisposition,
  phase: LifecyclePhase
): string {
  if (disposition === "human_review") {
    return phase === "verified"
      ? "Review request recorded · Unresolved — held for a person"
      : "Unresolved — held for a person";
  }
  const stop = disposition === "stop_proposed";
  switch (phase) {
    case "proposed":
      return "Proposed · not recorded";
    case "recorded":
      return stop ? "Stop proposal recorded · readback pending · not stopped" : "Recorded · readback pending";
    case "verified":
      return stop
        ? "Stop proposal recorded · readback verified ✓ · not stopped"
        : "Recorded · readback verified ✓";
  }
}

/** Exact row copy for a real backend write/readback milestone. */
export function writebackMarker(
  disposition: DecisionDisposition,
  progress: WritebackEntityProgressDTO
): string {
  switch (progress.phase) {
    case "PENDING":
      return "Proposed · not recorded";
    case "WRITING":
      return "Writing to DataHub…";
    case "WRITTEN":
      return "Written · verifying readback";
    case "VERIFYING_MCP":
      return "Verifying MCP tag readback";
    case "MCP_VERIFIED":
      return "MCP verified · verifying SDK readback";
    case "VERIFYING_SDK":
      return "Verifying SDK property readback";
    case "SDK_VERIFIED":
      return "Both readbacks verified";
    case "VERIFIED":
      return lifecycleMarker(disposition, "verified");
    case "FAILED":
      return `Failed · ${progress.failure?.safe_message ?? "Writeback did not complete"}`;
  }
}

export function mapChange(dto: ChangeDetailDTO): ChangeSummary {
  return {
    provider: dto.provider,
    obligationId: dto.obligation_id,
    changeId: dto.change_id ?? undefined,
    fromVersion: dto.previous_version,
    toVersion: dto.candidate_version,
    effectiveDate: dto.effective_date ?? undefined,
    reviewState: dto.review_state
  };
}

export function mapClauses(dto: ChangeDetailDTO): Clause[] {
  return dto.material_changes.map((c) => ({
    text: `"${c.rule_text}"`,
    effect: clauseEffectFromDTO(c.effect)
  }));
}

export function evidenceSummaryLine(e: ChangeEvidenceDTO): string {
  return `Evidence ${e.status} · ${e.rule_count} rules · ${e.gap_count} gaps`;
}

export function mapGovernedSource(dto: GovernedSourceDTO): GovernedSourceReference {
  return {
    displayName: dto.display_name,
    nativeType: dto.native_type,
    urn: dto.urn ?? undefined,
    resolved: dto.resolved,
    pendingLabel: "Source reference · pending DataHub resolution"
  };
}

export function mapTerminal(dto: TerminalDecisionDTO): TerminalPath {
  return {
    pathId: dto.path_id,
    id: dto.decision_id,
    responseIdentity: dto.response_identity,
    displayName: dto.display_name,
    assetType: dto.native_type,
    urn: dto.urn ?? undefined,
    owner: dto.owner ?? undefined,
    usageClass: dto.usage_class,
    disposition: dispositionFromDTO(dto.disposition),
    decisionRequirement: DECISION_REQUIREMENT[dispositionFromDTO(dto.disposition)],
    proposedAction: dto.proposed_action,
    triggeringRule: dto.triggering_rule,
    explanation: dto.explanation,
    hops: dto.hops.map((h) => ({
      name: h.name,
      assetType: h.native_type,
      urn: h.urn ?? undefined
    })),
    verificationState: dto.path_verification_state ?? undefined,
    evidenceAvailable: dto.evidence_state === "available",
    datahubUrl: dto.datahub_url ?? undefined,
    recorded: dto.recorded,
    readbackVerified: dto.readback_verified
  };
}

export function mapTerminals(dto: ImpactPlanDTO): TerminalPath[] {
  return dto.terminals.map(mapTerminal);
}

export function mapTally(terminals: TerminalPath[]): TallyCounts {
  const t: TallyCounts = { allowed: 0, remediate: 0, stopProposed: 0, humanReview: 0 };
  for (const term of terminals) {
    if (term.disposition === "allowed") t.allowed++;
    else if (term.disposition === "remediate") t.remediate++;
    else if (term.disposition === "stop_proposed") t.stopProposed++;
    else if (term.disposition === "human_review") t.humanReview++;
  }
  return t;
}

export function mapRows(
  terminals: TerminalPath[],
  phase: LifecyclePhase | ((id: string) => LifecyclePhase),
  selectedId: string | null,
  entityProgress: WritebackEntityProgressDTO[] = []
): ImpactPlanRowVM[] {
  const phaseOf = (id: string): LifecyclePhase =>
    typeof phase === "function" ? phase(id) : phase;
  const progressById = new Map(
    entityProgress.map((progress) => [progress.entity_id, progress])
  );
  return terminals.map((t, i) => {
    const p = phaseOf(t.id);
    const progress = progressById.get(t.id);
    return {
      id: t.id,
      index: i + 1,
      displayName: t.displayName,
      assetType: t.assetType,
      owner: t.owner,
      disposition: t.disposition,
      decisionRequirement: t.decisionRequirement,
      lifecycleMarker: progress
        ? writebackMarker(t.disposition, progress)
        : lifecycleMarker(t.disposition, p),
      human: t.disposition === "human_review",
      selected: t.id === selectedId,
      verified: progress?.phase === "VERIFIED" || p === "verified",
      writebackPhase: progress?.phase,
      failureMessage: progress?.failure?.safe_message,
      responseIdentity: t.responseIdentity,
      urn: t.urn,
      datahubUrl: t.datahubUrl
    };
  });
}

export function mapUnaffected(
  dto: UnaffectedControlDTO,
  verified: boolean
): UnaffectedControlVM {
  return {
    displayName: dto.display_name,
    assetType: dto.native_type,
    urn: dto.urn ?? undefined,
    note:
      verified && dto.unmutated_proof
        ? "Outside affected set · verified unmutated"
        : "Outside affected set",
    verified
  };
}

/** Owner fallback used across surfaces. */
export function ownerLabel(owner?: string): string {
  return owner ?? "Owner unavailable";
}

/**
 * Decision-first evidence bundle. Primary = triggering clause, lineage path,
 * proposed response. Secondary (expandable) = why, owner, raw rule id, native
 * type, URN, provenance. Unavailable fields are shown honestly, never faked.
 */
export function mapEvidence(dto: EvidenceBundleDTO, terminalName: string): EvidenceBundleVM {
  if (!dto.available) {
    return {
      terminalId: dto.terminal_ref,
      terminalName,
      usage: `usage · ${dto.usage_class}`,
      available: false,
      primary: [],
      secondary: [],
      datahubUrl: dto.datahub_url ?? undefined
    };
  }
  return {
    terminalId: dto.terminal_ref,
    terminalName,
    usage: `usage · ${dto.usage_class}`,
    available: true,
    primary: [
      { k: "Triggering clause", v: `"${dto.triggering_clause}"`, italic: true },
      { k: "DataHub lineage path", v: dto.lineage_path.join(" → "), mono: true },
      { k: "Proposed response", v: dto.proposed_action }
    ],
    secondary: [
      { k: "Why this disposition", v: dto.why_disposition },
      { k: "Owner", v: ownerLabel(dto.owner ?? undefined), mono: true },
      { k: "Raw rule id", v: dto.raw_rule_id || "not exposed", mono: true },
      { k: "Native type", v: dto.native_type, mono: true },
      { k: "URN", v: dto.urn ?? "not exposed", mono: true },
      { k: "Path verification", v: dto.verification_state ?? "not exposed", mono: true },
      { k: "Provenance", v: dto.provenance }
    ],
    datahubUrl: dto.datahub_url ?? undefined
  };
}
