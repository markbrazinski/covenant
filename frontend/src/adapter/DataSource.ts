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

export type Unsubscribe = () => void;

/** A recoverable operation the UI can ask the adapter to retry. */
export type RetryableOp = "activate" | "record" | "resolve_lineage";

/**
 * The seam between the Covenant frontend and its data.
 *
 * Components and the state machine depend ONLY on this interface — never on a
 * concrete transport. The preview ships `PreviewDataSource` (deterministic, no
 * network). The repository agent implements the SAME interface against the real
 * Gate 3 API and swaps it in at the single composition point (see App / useCovenant).
 *
 * Methods express intent, not routes. Progress is observed via subscriptions so
 * the real adapter can drive state from streamed backend responses, while the
 * preview yields a scripted deterministic sequence. State transitions are NEVER
 * owned by wall-clock timers in the application — only the adapter decides when
 * a phase advances.
 */
export interface CovenantDataSource {
  /** Retrieve the canonical reviewed change (Frame A content, no affected set). */
  getChange(): Promise<ChangeDetailDTO>;

  /** Retrieve change evidence summary (rules parsed, gaps). */
  getChangeEvidence(): Promise<ChangeEvidenceDTO>;

  /** The governed source reference; `resolved:false` until analysis resolves it. */
  getGovernedSource(): Promise<GovernedSourceDTO>;

  /**
   * Authorize impact analysis only. Returns the run id. Does not enact, approve,
   * or execute the obligation change. Begins emitting run progress to observers.
   */
  activate(): Promise<ActivationAck>;

  /**
   * Rehydrate an already-derived backend run after a direct impact-route load.
   * This is read-only: it must never activate a candidate or supply fixtures.
   */
  resumeImpact(): Promise<boolean>;

  /** Observe analysis-run progress (resolve → reconstruct → read → derive → complete). */
  observeRun(listener: (p: RunProgressDTO) => void): Unsubscribe;

  /**
   * Observe backend-projected errors (DataHub/MCP unavailable, evidence
   * unavailable, partial write). The adapter — not the UI — decides when a
   * failure occurs; the machine clears the affected set on DataHub failure.
   */
  observeErrors(listener: (e: ErrorProjectionDTO) => void): Unsubscribe;

  /** Cancel pending impact polling/network presentation for navigation or unmount. */
  cancelPending(): void;

  /** Retrieve the completed Impact Plan (terminals + unaffected control). */
  getImpactPlan(runId?: string): Promise<ImpactPlanDTO>;

  /** Retrieve durable, reconciled plans projected from the persisted API run store. */
  getRecordedPlans(): Promise<RecordedPlanDTO[]>;

  /** Retrieve full detail for a single terminal decision. */
  getTerminalDetail(decisionId: string): Promise<TerminalDecisionDTO>;

  /** Retrieve the decision-detail evidence bundle for a terminal. */
  getEvidence(decisionId: string): Promise<EvidenceBundleDTO>;

  /**
   * Record the proposed responses in DataHub. Records recommendations and
   * evidence only — does not approve or execute any response. Begins emitting
   * recording progress to observers.
   */
  recordProposedResponses(decisionIds: string[]): Promise<void>;

  /** Observe recording + readback-verification progress (incl. partial write). */
  observeRecording(listener: (p: RecordingProgressDTO) => void): Unsubscribe;

  /** Read back verified receipts once reconciliation reports success. */
  getReceipts(): Promise<VerifiedReceiptDTO[]>;

  /** Retry a partial or unavailable operation through the adapter. */
  retry(op: RetryableOp): Promise<void>;

  /** Reset/replay the canonical run. Stable replay preserves IDs and timestamps. */
  reset(): Promise<void>;
}
