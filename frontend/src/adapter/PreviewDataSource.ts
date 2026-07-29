/**
 * DETERMINISTIC PREVIEW ADAPTER — the demo's data source.
 *
 * Implements the production `CovenantDataSource` interface with no network. It
 * yields a scripted, deterministic asynchronous sequence so the flow can be
 * exercised without the Covenant backend. Timers live ONLY here (never in the
 * application) and exist purely to demonstrate causal progression; the real
 * adapter drives the same observers from streamed backend responses.
 *
 * REPOSITORY AGENT: replace this file with a real adapter implementing
 * CovenantDataSource against the Gate 3 API. Nothing else in the app changes.
 */
import type { CovenantDataSource, Unsubscribe, RetryableOp } from "./DataSource";
import type {
  ChangeDetailDTO,
  ChangeEvidenceDTO,
  GovernedSourceDTO,
  ActivationAck,
  RunProgressDTO,
  ImpactPlanDTO,
  TerminalDecisionDTO,
  EvidenceBundleDTO,
  RecordingProgressDTO,
  VerifiedReceiptDTO,
  ErrorProjectionDTO,
  RecordedPlanDTO
} from "./contracts";
import * as C from "../data/canonical";

/** Preview-only fault injection so the demo can exercise failure states. */
export type PreviewFault = "none" | "datahub_unavailable" | "evidence_unavailable" | "partial_write";

export interface PreviewOptions {
  fault?: PreviewFault;
  /** step duration in ms; 0 → instant (used for reduced-motion / tests). */
  step?: number;
}

const TIERS_TOTAL = 3; // completed-result presentation geometry only

export class PreviewDataSource implements CovenantDataSource {
  private fault: PreviewFault;
  private step: number;
  private runListeners = new Set<(p: RunProgressDTO) => void>();
  private recListeners = new Set<(p: RecordingProgressDTO) => void>();
  private errListeners = new Set<(e: ErrorProjectionDTO) => void>();
  private timers: ReturnType<typeof setTimeout>[] = [];
  private recordedIds = new Set<string>();
  private verifiedIds = new Set<string>();
  private partialTriggered = false;

  constructor(opts: PreviewOptions = {}) {
    this.fault = opts.fault ?? "none";
    this.step = opts.step ?? 620;
  }

  // ---- preview-only controls (not part of CovenantDataSource) -------------
  setFault(f: PreviewFault) {
    this.fault = f;
  }
  setStep(ms: number) {
    this.step = ms;
  }

  // ---- reads --------------------------------------------------------------
  getChange(): Promise<ChangeDetailDTO> {
    return Promise.resolve(clone(C.change));
  }
  getChangeEvidence(): Promise<ChangeEvidenceDTO> {
    return Promise.resolve(clone(C.evidence));
  }
  getGovernedSource(): Promise<GovernedSourceDTO> {
    return Promise.resolve(clone(C.governedSource));
  }
  getImpactPlan(): Promise<ImpactPlanDTO> {
    return Promise.resolve(clone(C.impactPlan));
  }
  getRecordedPlans(): Promise<RecordedPlanDTO[]> {
    return Promise.resolve([]);
  }
  getTerminalDetail(id: string): Promise<TerminalDecisionDTO> {
    const t = C.impactPlan.terminals.find((x) => x.decision_id === id);
    if (!t) return Promise.reject(new Error(`unknown terminal ${id}`));
    return Promise.resolve(clone(t));
  }
  getEvidence(id: string): Promise<EvidenceBundleDTO> {
    if (this.fault === "evidence_unavailable") {
      return Promise.resolve({ ...unavailableEvidence(id) });
    }
    if (id === "churn_model_a") return Promise.resolve(clone(C.churnEvidence));
    return Promise.resolve(evidenceFromTerminal(id));
  }

  // ---- observation --------------------------------------------------------
  observeRun(l: (p: RunProgressDTO) => void): Unsubscribe {
    this.runListeners.add(l);
    return () => this.runListeners.delete(l);
  }
  observeRecording(l: (p: RecordingProgressDTO) => void): Unsubscribe {
    this.recListeners.add(l);
    return () => this.recListeners.delete(l);
  }
  observeErrors(l: (e: ErrorProjectionDTO) => void): Unsubscribe {
    this.errListeners.add(l);
    return () => this.errListeners.delete(l);
  }
  cancelPending(): void {
    this.timers.forEach(clearTimeout);
    this.timers = [];
  }

  // ---- run ----------------------------------------------------------------
  activate(): Promise<ActivationAck> {
    const runId = C.impactPlan.run_id;
    // Explicit fixture mode still preserves the real coarse truth boundary.
    let k = 1;
    const at = (fn: () => void) => this.timers.push(setTimeout(fn, this.step * k++));

    at(() =>
      this.emitRun({
        phase: "resolving_impact",
        server_stage: "RESOLVING_IMPACT",
        server_message: "Resolving impact through DataHub",
        source_resolution_status: "Governed source unresolved",
        tiers_resolved: 0,
        tiers_total: 0,
        terminals_revealed: 0,
        downstream_entity_count: null,
        terminal_path_count: null
      })
    );

    if (this.fault === "datahub_unavailable") {
      at(() =>
        this.emitError({
          code: "DATAHUB_UNAVAILABLE",
          title: "DataHub unavailable",
          detail:
            "Lineage could not be read from the MCP server. Impact analysis cannot proceed.",
          clears_affected_set: true
        })
      );
      return Promise.resolve({ run_id: runId, authorized: true });
    }

    const n = C.impactPlan.terminals.length;
    at(() =>
      this.emitRun({
        phase: "complete",
        server_stage: "IMPACT_READY",
        server_message: "Five graph-derived responses are ready",
        source_resolution_status: "Resolved live through DataHub",
        tiers_resolved: TIERS_TOTAL,
        tiers_total: TIERS_TOTAL,
        terminals_revealed: n,
        downstream_entity_count: C.impactPlan.downstream_entity_count,
        terminal_path_count: C.impactPlan.terminal_path_count
      })
    );
    return Promise.resolve({ run_id: runId, authorized: true });
  }

  resumeImpact(): Promise<boolean> {
    return Promise.resolve(false);
  }

  // ---- recording ----------------------------------------------------------
  recordProposedResponses(ids: string[]): Promise<void> {
    const target = ids.length;
    let k = 1;
    const at = (fn: () => void) => this.timers.push(setTimeout(fn, this.step * k++));
    const emit = (
      phase: RecordingProgressDTO["phase"],
      incomplete: string[]
    ) =>
      this.emitRec({
        run_id: C.impactPlan.run_id,
        phase,
        target_count: target,
        recorded_count: this.recordedIds.size,
        readback_verified_count: this.verifiedIds.size,
        recorded_ids: [...this.recordedIds],
        verified_ids: [...this.verifiedIds],
        incomplete_ids: incomplete,
        stable_replay: phase === "reconciled"
      });

    const partial = this.fault === "partial_write" && !this.partialTriggered;
    // how many succeed on this attempt
    const recordTarget = partial ? Math.min(3, target) : target;
    const verifyTarget = partial ? Math.min(2, target) : target;

    for (let i = 0; i < ids.length; i++) {
      if (i < recordTarget) {
        const id = ids[i];
        at(() => {
          this.recordedIds.add(id);
          emit("recording", ids.filter((x) => !this.recordedIds.has(x)));
        });
      }
    }
    for (let i = 0; i < ids.length; i++) {
      if (i < verifyTarget) {
        const id = ids[i];
        at(() => {
          this.verifiedIds.add(id);
          emit("verifying_readbacks", ids.filter((x) => !this.verifiedIds.has(x)));
        });
      }
    }

    if (partial) {
      this.partialTriggered = true;
      at(() => {
        const incomplete = ids.filter((x) => !this.verifiedIds.has(x));
        emit("partial", incomplete);
        this.emitError({
          code: "PARTIAL_WRITE",
          title: "Partial write",
          detail:
            "Some proposed responses recorded; others remain incomplete. Recording did not approve or execute anything. Retry is safe and preserves identities.",
          clears_affected_set: false
        });
      });
    } else {
      at(() => emit("reconciled", []));
    }
    return Promise.resolve();
  }

  getReceipts(): Promise<VerifiedReceiptDTO[]> {
    return Promise.resolve(clone(C.receipts));
  }

  // ---- recovery -----------------------------------------------------------
  retry(op: RetryableOp): Promise<void> {
    if (op === "resolve_lineage" || op === "activate") {
      this.fault = "none";
      return this.activate().then(() => undefined);
    }
    if (op === "record") {
      // resume only the incomplete ids — no duplicate identities
      const remaining = C.impactPlan.terminals
        .map((t) => t.decision_id)
        .filter((id) => !this.verifiedIds.has(id));
      this.fault = "none";
      return this.recordProposedResponses(remaining);
    }
    return Promise.resolve();
  }

  reset(): Promise<void> {
    this.cancelPending();
    this.recordedIds.clear();
    this.verifiedIds.clear();
    this.partialTriggered = false;
    return Promise.resolve();
  }

  // ---- emit helpers -------------------------------------------------------
  private emitRun(partial: Omit<RunProgressDTO, "run_id">) {
    const p: RunProgressDTO = { run_id: C.impactPlan.run_id, ...partial };
    this.runListeners.forEach((l) => l(p));
  }
  private emitRec(p: RecordingProgressDTO) {
    this.recListeners.forEach((l) => l(p));
  }
  private emitError(e: ErrorProjectionDTO) {
    this.errListeners.forEach((l) => l(e));
  }
}

function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}

function evidenceFromTerminal(id: string): EvidenceBundleDTO {
  const t = C.impactPlan.terminals.find((x) => x.decision_id === id);
  if (!t) return unavailableEvidence(id);
  return {
    terminal_ref: id,
    usage_class: t.usage_class,
    triggering_clause: t.triggering_rule,
    lineage_path: t.path,
    proposed_action: t.proposed_action,
    why_disposition: t.explanation,
    owner: t.owner,
    raw_rule_id: "", // rule id not exposed for non-canonical terminals → "not exposed"
    native_type: t.native_type,
    urn: t.urn,
    provenance: "lineage & ownership via MCP · usage & terminal via DataHub SDK",
    verification_state: t.path_verification_state,
    readback_state: t.readback_state,
    datahub_url: t.datahub_url,
    available: true
  };
}

function unavailableEvidence(id: string): EvidenceBundleDTO {
  const t = C.impactPlan.terminals.find((x) => x.decision_id === id);
  return {
    terminal_ref: id,
    usage_class: t?.usage_class ?? "unknown",
    triggering_clause: "",
    lineage_path: [],
    proposed_action: "",
    why_disposition: "",
    owner: null,
    raw_rule_id: "",
    native_type: t?.native_type ?? "",
    urn: null,
    provenance: "",
    verification_state: null,
    readback_state: null,
    datahub_url: null,
    available: false
  };
}
