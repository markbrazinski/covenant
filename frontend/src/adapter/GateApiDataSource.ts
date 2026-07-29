import type { CovenantDataSource, RetryableOp, Unsubscribe } from "./DataSource";
import type {
  ActivationAck,
  ChangeDetailDTO,
  ChangeEvidenceDTO,
  ErrorProjectionDTO,
  EvidenceBundleDTO,
  GovernedSourceDTO,
  ImpactPlanDTO,
  RecordedPlanDTO,
  RecordingProgressDTO,
  RunProgressDTO,
  TerminalDecisionDTO,
  VerifiedReceiptDTO,
  WritebackEntityProgressDTO,
  WritebackProgressDTO
} from "./contracts";

interface GateApiConfig {
  baseUrl: string;
  pollIntervalMs?: number;
  changeId?: string;
}

interface ApiChangeSummary {
  change_id: string;
  obligation_id: string;
  provider_name: string;
  superseded_version: number;
  candidate_version: number;
  effective_at: string;
  source_asset: { urn: string; display_name: string; native_type: string };
  lifecycle_state: string;
  evidence_state: string;
  material_rule_count: number;
  unresolved_gap_count: number;
  candidate_hash: string;
}

interface ApiChangeDetail {
  summary: ApiChangeSummary;
  candidate: {
    rules: Array<{
      usage_class: string;
      effect: string;
      citation: { quote: string };
    }>;
  };
}

interface ApiPathNode {
  urn: string;
  display_name: string;
  native_type: string;
}

interface ApiDecision {
  path_id: string;
  decision_id: string;
  asset_urn: string;
  display_name: string;
  native_type: string;
  owner: string | null;
  usage_class: string | null;
  disposition: string;
  decision_state: string;
  proposed_action: string;
  paths: string[][];
  path_nodes: ApiPathNode[][];
  triggering_rule: {
    citation?: { quote?: string };
  };
  controlling_policy_rule: string;
  confidence_meaning: string;
  actor_class: string;
  metadata_interfaces: Record<string, string>;
  mcp_path_verified: boolean;
  readback_verified: boolean;
  datahub_url: string | null;
}

interface ApiReceipt {
  decision_id: string;
  asset_urn: string;
  written: boolean;
  mcp_tag_readback_verified: boolean;
  sdk_receipt_readback_verified: boolean;
  stable_recorded_at: boolean;
  duplicate_tags: boolean;
  recorded_at: string | null;
  datahub_url: string | null;
}

interface ApiRun {
  run_id: string;
  change_id: string;
  activation_id: string;
  stage: string;
  progress: {
    stage: string;
    message: string;
    completed: number;
    total: number;
    error: ApiError | null;
  };
  source: {
    urn: string;
    resolved_via: string;
    obligation_id: string;
    active_version: number;
  } | null;
  graph: {
    downstream_entity_count: number;
    terminal_count: number;
    read_interface: string;
  } | null;
  decisions: ApiDecision[];
  receipts: ApiReceipt[];
  reconciliation_verified: boolean;
  unaffected_control: {
    asset_urn: string;
    display_name: string;
    native_type: string;
    outside_affected_set_proof: string;
    unmutated_verified: boolean;
    datahub_url: string | null;
  } | null;
}

interface ApiError {
  code: string;
  message: string;
  affected_set_produced: boolean | null;
  retryable: boolean;
}

const SYNTHETIC_APPROVAL = "SYNTHETIC TEST APPROVAL";
const SYNTHETIC_ACTOR = "synthetic_gate5_reviewer";

export class GateApiDataSource implements CovenantDataSource {
  private readonly baseUrl: string;
  private readonly pollIntervalMs: number;
  private readonly changeId: string | null;
  private change: ApiChangeDetail | null = null;
  private run: ApiRun | null = null;
  private plan: ImpactPlanDTO | null = null;
  private runListeners = new Set<(p: RunProgressDTO) => void>();
  private recordingListeners = new Set<(p: RecordingProgressDTO) => void>();
  private errorListeners = new Set<(e: ErrorProjectionDTO) => void>();
  private slugToDecision = new Map<string, string>();
  private decisionToSlug = new Map<string, string>();
  private operationId = 0;
  private runEpoch = 0;
  private impactController: AbortController | null = null;
  private pollController: AbortController | null = null;

  constructor(config: GateApiConfig) {
    this.baseUrl = config.baseUrl.replace(/\/+$/, "");
    this.pollIntervalMs = config.pollIntervalMs ?? 150;
    this.changeId = config.changeId ?? null;
  }

  async getChange(): Promise<ChangeDetailDTO> {
    const detail = await this.loadChange();
    return {
      change_id: detail.summary.change_id,
      provider: detail.summary.provider_name,
      obligation_id: detail.summary.obligation_id,
      previous_version: detail.summary.superseded_version,
      candidate_version: detail.summary.candidate_version,
      effective_date: detail.summary.effective_at,
      review_state: detail.summary.lifecycle_state,
      material_changes: detail.candidate.rules.map((rule) => ({
        rule_text: stripBullet(rule.citation.quote),
        effect:
          rule.effect === "prohibited"
            ? "PROHIBITED"
            : rule.effect === "review_required"
              ? "REVIEW"
              : "ALLOWED"
      }))
    };
  }

  async getChangeEvidence(): Promise<ChangeEvidenceDTO> {
    const { summary } = await this.loadChange();
    return {
      status: summary.evidence_state,
      rule_count: summary.material_rule_count,
      gap_count: summary.unresolved_gap_count
    };
  }

  async getGovernedSource(): Promise<GovernedSourceDTO> {
    const { summary } = await this.loadChange();
    return {
      display_name: summary.source_asset.display_name,
      native_type: summary.source_asset.native_type,
      urn: summary.source_asset.urn,
      resolved: false
    };
  }

  observeRun(listener: (p: RunProgressDTO) => void): Unsubscribe {
    this.runListeners.add(listener);
    return () => this.runListeners.delete(listener);
  }

  observeRecording(listener: (p: RecordingProgressDTO) => void): Unsubscribe {
    this.recordingListeners.add(listener);
    return () => this.recordingListeners.delete(listener);
  }

  observeErrors(listener: (e: ErrorProjectionDTO) => void): Unsubscribe {
    this.errorListeners.add(listener);
    return () => this.errorListeners.delete(listener);
  }

  cancelPending(): void {
    this.operationId += 1;
    this.impactController?.abort();
    this.pollController?.abort();
    this.impactController = null;
    this.pollController = null;
  }

  async activate(): Promise<ActivationAck> {
    this.cancelPending();
    const operationId = this.operationId;
    const impactController = new AbortController();
    const pollController = new AbortController();
    this.impactController = impactController;
    this.pollController = pollController;
    try {
      const detail = await this.loadChange();
      if (!this.isCurrentOperation(operationId)) return this.currentAck();
      let activated: ApiRun;
      if (detail.summary.lifecycle_state === "ACTIVE") {
        const existing = await this.request<ApiRun[]>("/api/runs", {
          signal: impactController.signal
        });
        const run = existing.find((item) => item.change_id === detail.summary.change_id);
        if (!run) throw new Error("The active change has no persisted run.");
        activated = run;
      } else {
        activated = await this.request<ApiRun>(
          `/api/changes/${encodeURIComponent(detail.summary.change_id)}/activate`,
          {
            method: "POST",
            body: JSON.stringify({
              reviewed_candidate_hash: detail.summary.candidate_hash,
              label: SYNTHETIC_APPROVAL,
              actor: SYNTHETIC_ACTOR,
              review_note:
                "Gate 5 UI software test only; no real legal or governance approval."
            }),
            signal: impactController.signal
          }
        );
      }
      if (!this.isCurrentOperation(operationId)) return this.currentAck(activated);
      this.beginRun(activated);
      if (activated.stage === "ACTIVE") {
        this.emitRun(this.progressFromServer(activated));
      }

      const impactPromise = this.request<ApiRun>(
        `/api/changes/${encodeURIComponent(detail.summary.change_id)}/impact`,
        { method: "POST", signal: impactController.signal }
      );
      const polling = this.pollRun(
        activated.run_id,
        operationId,
        pollController.signal
      );
      const [impact] = await Promise.all([impactPromise, polling]);
      if (!this.isCurrentOperation(operationId)) return this.currentAck(impact);
      pollController.abort();
      this.assertSameRun(activated, impact);
      this.setRun(impact);
      this.emitRun(this.completedProgress(impact));
      return { run_id: impact.run_id, authorized: true };
    } catch (error) {
      impactController.abort();
      pollController.abort();
      if (isAbortError(error) || !this.isCurrentOperation(operationId)) {
        return this.currentAck();
      }
      this.emitApiError(error, true);
      throw error;
    } finally {
      if (this.isCurrentOperation(operationId)) {
        this.impactController = null;
        this.pollController = null;
      }
    }
  }

  async resumeImpact(): Promise<boolean> {
    try {
      const detail = await this.loadChange();
      const runs = await this.request<ApiRun[]>("/api/runs");
      const resumable = [...runs]
        .reverse()
        .find(
          (run) =>
            run.change_id === detail.summary.change_id &&
            run.source !== null &&
            run.decisions.length > 0
        );
      if (!resumable) return false;
      this.setRun(resumable);
      this.emitRun(this.completedProgress(resumable));
      if (resumable.progress.error) {
        this.emitApiError(
          new ApiRequestError(resumable.progress.error),
          false
        );
      }
      return true;
    } catch (error) {
      this.emitApiError(error, true);
      return false;
    }
  }

  async getImpactPlan(runId?: string): Promise<ImpactPlanDTO> {
    if (runId) {
      const run = await this.request<ApiRun>(`/api/runs/${encodeURIComponent(runId)}`);
      this.setRun(run);
    }
    if (!this.plan) throw new Error("Impact Plan is not available before derivation.");
    return clone(this.plan);
  }

  async getRecordedPlans(): Promise<RecordedPlanDTO[]> {
    const runs = await this.request<ApiRun[]>("/api/runs");
    return runs
      .filter((run) => isReconciled(run))
      .map((run) => {
        const plan = this.mapPlan(run);
        return {
          run_id: run.run_id,
          change_id: run.change_id,
          recorded_at:
            run.receipts.map((item) => item.recorded_at).filter(isString).sort()[0] ?? null,
          plan,
          receipts: this.mapReceipts(run)
        };
      });
  }

  async getTerminalDetail(decisionId: string): Promise<TerminalDecisionDTO> {
    const plan = await this.getImpactPlan();
    const terminal = plan.terminals.find((item) => item.decision_id === decisionId);
    if (!terminal) throw new Error(`Unknown terminal ${decisionId}`);
    return clone(terminal);
  }

  async getEvidence(decisionId: string): Promise<EvidenceBundleDTO> {
    const terminal = await this.getTerminalDetail(decisionId);
    const decision = this.run?.decisions.find(
      (item) => item.decision_id === terminal.response_identity
    );
    if (!decision) return unavailableEvidence(terminal);
    const path = terminal.path;
    const provenance = [
      decision.metadata_interfaces.lineage,
      decision.metadata_interfaces.ownership,
      decision.metadata_interfaces.usage_and_terminal
    ]
      .filter(Boolean)
      .join(" · ");
    return {
      terminal_ref: terminal.decision_id,
      usage_class: terminal.usage_class,
      triggering_clause: terminal.triggering_rule,
      lineage_path: path,
      proposed_action: terminal.proposed_action,
      why_disposition: `${decision.confidence_meaning}; ${decision.controlling_policy_rule}`,
      owner: terminal.owner,
      raw_rule_id: decision.controlling_policy_rule,
      native_type: terminal.native_type,
      urn: terminal.urn,
      provenance,
      verification_state: terminal.path_verification_state,
      readback_state: terminal.readback_state,
      datahub_url: terminal.datahub_url,
      available: Boolean(terminal.triggering_rule && terminal.path.length)
    };
  }

  async recordProposedResponses(_decisionIds: string[]): Promise<void> {
    if (!this.run) throw new Error("Impact Plan is not available.");
    const currentRun = this.run;
    const runId = currentRun.run_id;
    const activationId = currentRun.activation_id;
    const epoch = this.runEpoch;
    let settled = false;
    let completedRun: ApiRun | null = null;
    let writeError: unknown = null;
    const writeRequest = this.request<ApiRun>(
        `/api/runs/${encodeURIComponent(runId)}/writeback`,
        { method: "POST" }
      )
      .then((run) => {
        completedRun = run;
      })
      .catch((error: unknown) => {
        writeError = error;
      })
      .finally(() => {
        settled = true;
      });

    let lastProgress: WritebackProgressDTO | null = null;
    let lastProgressSignature = "";
    while (epoch === this.runEpoch) {
      try {
        const progress = await this.request<WritebackProgressDTO>(
          `/api/runs/${encodeURIComponent(runId)}/writeback-progress`
        );
        if (epoch !== this.runEpoch) break;
        if (progress.run_id !== runId) {
          throw new Error("Writeback progress run identity changed.");
        }
        lastProgress = progress;
        const signature = progress.entities
          .map(
            (entity) =>
              `${entity.entity_id}:${entity.phase}:${entity.phase_started_at}`
          )
          .join("|");
        if (
          progress.entities.length > 0 &&
          signature !== lastProgressSignature
        ) {
          lastProgressSignature = signature;
          this.emitRecording(this.mapWritebackProgress(progress));
        }
      } catch (progressError) {
        if (settled) break;
        writeError = progressError;
        break;
      }
      if (settled) break;
      await abortableDelay(this.pollIntervalMs, new AbortController().signal);
    }
    await writeRequest;
    if (epoch !== this.runEpoch) return;

    if (completedRun) {
      this.assertRunIdentity(completedRun, runId, activationId);
      this.setRun(completedRun);
      if (!isReconciled(completedRun)) {
        writeError = new Error("Receipt reconciliation is incomplete.");
      } else if (!lastProgress?.terminal) {
        const finalProgress = await this.request<WritebackProgressDTO>(
          `/api/runs/${encodeURIComponent(runId)}/writeback-progress`
        );
        const finalSignature = finalProgress.entities
          .map(
            (entity) =>
              `${entity.entity_id}:${entity.phase}:${entity.phase_started_at}`
          )
          .join("|");
        if (finalSignature !== lastProgressSignature) {
          this.emitRecording(this.mapWritebackProgress(finalProgress));
        }
      }
    }
    if (writeError) {
      try {
        const partial = await this.request<ApiRun>(
          `/api/runs/${encodeURIComponent(runId)}`
        );
        if (epoch !== this.runEpoch) return;
        this.assertRunIdentity(partial, runId, activationId);
        this.setRun(partial);
      } catch (readError) {
        if (epoch !== this.runEpoch) return;
        this.emitApiError(readError, false);
        return;
      }
      this.emitApiError(writeError, false);
    }
  }

  async getReceipts(): Promise<VerifiedReceiptDTO[]> {
    if (!this.run) return [];
    const runId = this.run.run_id;
    const activationId = this.run.activation_id;
    const epoch = this.runEpoch;
    const fresh = await this.request<ApiRun>(
      `/api/runs/${encodeURIComponent(runId)}`
    );
    if (epoch !== this.runEpoch) return [];
    this.assertRunIdentity(fresh, runId, activationId);
    this.setRun(fresh);
    return this.mapReceipts(fresh);
  }

  async retry(op: RetryableOp): Promise<void> {
    if (op === "record") return this.recordProposedResponses([]);
    await this.activate();
  }

  async reset(): Promise<void> {
    if (!this.run) return;
    this.cancelPending();
    const runId = this.run.run_id;
    const activationId = this.run.activation_id;
    const epoch = ++this.runEpoch;
    const replay = await this.request<ApiRun>(
      `/api/runs/${encodeURIComponent(runId)}/replay`,
      { method: "POST" }
    );
    if (epoch !== this.runEpoch) return;
    this.assertRunIdentity(replay, runId, activationId);
    this.setRun(replay);
  }

  private async loadChange(): Promise<ApiChangeDetail> {
    if (this.change) return this.change;
    if (this.changeId) {
      this.change = await this.request<ApiChangeDetail>(
        `/api/changes/${encodeURIComponent(this.changeId)}`
      );
      return this.change;
    }
    const changes = await this.request<ApiChangeSummary[]>("/api/changes");
    if (changes.length !== 1) throw new Error(`Expected one change, received ${changes.length}.`);
    this.change = await this.request<ApiChangeDetail>(
      `/api/changes/${encodeURIComponent(changes[0].change_id)}`
    );
    return this.change;
  }

  private setRun(run: ApiRun) {
    this.run = run;
    this.runEpoch += 1;
    this.plan = run.decisions.length ? this.mapPlan(run) : null;
  }

  private beginRun(run: ApiRun) {
    this.run = run;
    this.runEpoch += 1;
    this.plan = null;
    this.slugToDecision.clear();
    this.decisionToSlug.clear();
  }

  private mapPlan(run: ApiRun): ImpactPlanDTO {
    this.slugToDecision.clear();
    this.decisionToSlug.clear();
    const receipts = new Map(run.receipts.map((item) => [item.decision_id, item]));
    const terminals = run.decisions.map((decision) => {
      const slug = stableTerminalSlug(decision.asset_urn);
      this.slugToDecision.set(slug, decision.decision_id);
      this.decisionToSlug.set(decision.decision_id, slug);
      const pathNodes = decision.path_nodes[0] ?? [];
      const path = pathNodes.map((node) => node.display_name);
      const receipt = receipts.get(decision.decision_id);
      return {
        path_id: decision.path_id,
        decision_id: slug,
        response_identity: decision.decision_id,
        display_name: decision.display_name,
        native_type: decision.native_type,
        urn: decision.asset_urn,
        owner: decision.owner,
        usage_class: decision.usage_class ?? "unknown",
        disposition: decision.disposition,
        decision_state: decision.decision_state,
        proposed_action: decision.proposed_action,
        triggering_rule: stripBullet(decision.triggering_rule.citation?.quote ?? ""),
        explanation: `${decision.confidence_meaning}; ${decision.controlling_policy_rule}`,
        path,
        hops: pathNodes.slice(1, -1).map((node) => ({
          name: node.display_name,
          native_type: node.native_type,
          urn: node.urn
        })),
        path_verification_state: decision.mcp_path_verified
          ? "MCP path verified"
          : null,
        evidence_state: decision.triggering_rule.citation?.quote ? "available" : "unavailable",
        readback_state:
          receipt &&
          receipt.mcp_tag_readback_verified &&
          receipt.sdk_receipt_readback_verified
            ? "MCP tag + SDK receipt verified"
            : null,
        datahub_url: dataHubPropertiesUrl(decision.datahub_url),
        recorded: Boolean(receipt?.written),
        readback_verified: Boolean(
          receipt?.mcp_tag_readback_verified &&
            receipt.sdk_receipt_readback_verified
        )
      } satisfies TerminalDecisionDTO;
    });
    return {
      run_id: run.run_id,
      source_resolution_status: run.source?.resolved_via ?? "DataHub source unavailable",
      downstream_entity_count: run.graph?.downstream_entity_count ?? null,
      terminal_path_count: run.graph?.terminal_count ?? terminals.length,
      terminals,
      unaffected_control: run.unaffected_control
        ? {
            display_name: run.unaffected_control.display_name,
            native_type: run.unaffected_control.native_type,
            urn: run.unaffected_control.asset_urn,
            outside_affected_set_proof:
              run.unaffected_control.outside_affected_set_proof,
            unmutated_proof: run.unaffected_control.unmutated_verified
              ? "verified unmutated"
              : null,
            datahub_url: dataHubPropertiesUrl(run.unaffected_control.datahub_url)
          }
        : null
    };
  }

  private mapReceipts(run: ApiRun): VerifiedReceiptDTO[] {
    const decisionById = new Map(run.decisions.map((item) => [item.decision_id, item]));
    return run.receipts.map((receipt) => {
      const decision = decisionById.get(receipt.decision_id);
      return {
        decision_id:
          this.decisionToSlug.get(receipt.decision_id) ??
          stableTerminalSlug(receipt.asset_urn),
        response_identity: receipt.decision_id,
        target_name: decision?.display_name ?? receipt.asset_urn,
        target_urn: receipt.asset_urn,
        recorded: receipt.written,
        readback_verified:
          receipt.mcp_tag_readback_verified &&
          receipt.sdk_receipt_readback_verified,
        receipt_id: receipt.decision_id,
        recorded_at: receipt.recorded_at,
        datahub_url: dataHubPropertiesUrl(receipt.datahub_url)
      };
    });
  }

  private completedProgress(run: ApiRun): RunProgressDTO {
    const tiers = Math.max(
      1,
      ...run.decisions.map((decision) =>
        Math.max(0, (decision.path_nodes[0]?.length ?? 2) - 1)
      )
    );
    return {
      run_id: run.run_id,
      phase: "complete",
      server_stage: run.stage,
      server_message: run.progress.message,
      source_resolution_status:
        run.source?.resolved_via ?? "DataHub source unavailable",
      downstream_entity_count: run.graph?.downstream_entity_count ?? null,
      terminal_path_count: run.graph?.terminal_count ?? null,
      tiers_resolved: tiers,
      tiers_total: tiers,
      terminals_revealed: run.decisions.length
    };
  }

  private progressFromServer(run: ApiRun): RunProgressDTO {
    return {
      run_id: run.run_id,
      phase: "resolving_impact",
      server_stage: run.stage,
      server_message: run.progress.message,
      source_resolution_status: "Governed source unresolved",
      downstream_entity_count: null,
      terminal_path_count: null,
      tiers_resolved: 0,
      tiers_total: 0,
      terminals_revealed: 0
    };
  }

  private async pollRun(
    runId: string,
    operationId: number,
    signal: AbortSignal
  ): Promise<void> {
    while (!signal.aborted && this.isCurrentOperation(operationId)) {
      try {
        const current = await this.request<ApiRun>(
          `/api/runs/${encodeURIComponent(runId)}`,
          { signal }
        );
        if (!this.isCurrentOperation(operationId) || signal.aborted) return;
        if (current.run_id !== runId) {
          throw new Error("Polled run identity changed.");
        }
        if (current.stage === "ACTIVE" || current.stage === "RESOLVING_IMPACT") {
          this.emitRun(this.progressFromServer(current));
        }
        if (
          current.stage === "IMPACT_READY" ||
          current.stage === "IMPACT_UNAVAILABLE" ||
          current.stage === "DATAHUB_UNAVAILABLE"
        ) {
          return;
        }
        await abortableDelay(this.pollIntervalMs, signal);
      } catch (error) {
        if (isAbortError(error) || signal.aborted) return;
        throw error;
      }
    }
  }

  private isCurrentOperation(operationId: number): boolean {
    return operationId === this.operationId;
  }

  private currentAck(fallback?: ApiRun): ActivationAck {
    const current = this.run ?? fallback;
    return {
      run_id: current?.run_id ?? "cancelled",
      authorized: true
    };
  }

  private assertSameRun(expected: ApiRun, actual: ApiRun): void {
    this.assertRunIdentity(actual, expected.run_id, expected.activation_id);
  }

  private assertRunIdentity(
    actual: ApiRun,
    runId: string,
    activationId: string
  ): void {
    if (actual.run_id !== runId || actual.activation_id !== activationId) {
      throw new Error("Run or activation identity changed during the operation.");
    }
  }

  private mapWritebackProgress(
    progress: WritebackProgressDTO
  ): RecordingProgressDTO {
    const entityProgress: WritebackEntityProgressDTO[] =
      progress.entities.map((entity) => ({
        ...entity,
        entity_id:
          this.decisionToSlug.get(entity.entity_id) ?? entity.entity_id
      }));
    const verified = entityProgress
      .filter((entity) => entity.phase === "VERIFIED")
      .map((entity) => entity.entity_id);
    const recorded = entityProgress
      .filter((entity) => entity.response_id !== null)
      .map((entity) => entity.entity_id);
    const incomplete = entityProgress
      .filter((entity) => entity.phase !== "VERIFIED")
      .map((entity) => entity.entity_id);
    const verifying = entityProgress.some((entity) =>
      [
        "WRITTEN",
        "VERIFYING_MCP",
        "MCP_VERIFIED",
        "VERIFYING_SDK",
        "SDK_VERIFIED"
      ].includes(entity.phase)
    );
    return {
      run_id: progress.run_id,
      phase: progress.failed
        ? "partial"
        : progress.terminal
          ? "reconciled"
          : verifying
            ? "verifying_readbacks"
            : "recording",
      target_count: entityProgress.length,
      recorded_count: recorded.length,
      readback_verified_count: verified.length,
      recorded_ids: recorded,
      verified_ids: verified,
      incomplete_ids: incomplete,
      stable_replay: progress.terminal && !progress.failed,
      entity_progress: entityProgress
    };
  }

  private emitRun(progress: RunProgressDTO) {
    this.runListeners.forEach((listener) => listener(progress));
  }

  private emitRecording(progress: RecordingProgressDTO) {
    this.recordingListeners.forEach((listener) => listener(progress));
  }

  private emitApiError(error: unknown, clearsAffectedSet: boolean) {
    const api = error instanceof ApiRequestError ? error.payload : null;
    const projection: ErrorProjectionDTO = {
      code: api?.code ?? (clearsAffectedSet ? "DATAHUB_UNAVAILABLE" : "PARTIAL_WRITE"),
      title: clearsAffectedSet ? "DataHub unavailable" : "Partial write",
      detail: api?.message ?? (error instanceof Error ? error.message : "The operation failed."),
      clears_affected_set: clearsAffectedSet
    };
    this.errorListeners.forEach((listener) => listener(projection));
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers }
    });
    const payload = (await response.json()) as T | ApiError;
    if (!response.ok) throw new ApiRequestError(payload as ApiError);
    return payload as T;
  }
}

class ApiRequestError extends Error {
  constructor(readonly payload: ApiError) {
    super(payload.message);
  }
}

function stableTerminalSlug(urn: string): string {
  const matches = [...urn.matchAll(/northstar[.:]([a-z0-9_]+)/gi)];
  const northstar = matches[matches.length - 1];
  if (northstar?.[1]) return northstar[1].toLowerCase();
  return `terminal_${stableHash(urn)}`;
}

function stableHash(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}

function stripBullet(value: string): string {
  return value.replace(/^\s*-\s*/, "").trim();
}

export function isReconciled(run: ApiRun): boolean {
  const expected = new Map(
    run.decisions.map((decision) => [decision.decision_id, decision.asset_urn])
  );
  const actual = new Map(
    run.receipts.map((receipt) => [receipt.decision_id, receipt.asset_urn])
  );
  return (
    run.reconciliation_verified &&
    expected.size > 0 &&
    run.decisions.length === expected.size &&
    run.receipts.length === expected.size &&
    actual.size === expected.size &&
    [...expected].every(
      ([decisionId, assetUrn]) => actual.get(decisionId) === assetUrn
    ) &&
    run.receipts.every(
      (receipt) =>
        receipt.written &&
        receipt.mcp_tag_readback_verified &&
        receipt.sdk_receipt_readback_verified
    )
  );
}

function unavailableEvidence(terminal: TerminalDecisionDTO): EvidenceBundleDTO {
  return {
    terminal_ref: terminal.decision_id,
    usage_class: terminal.usage_class,
    triggering_clause: "",
    lineage_path: [],
    proposed_action: "",
    why_disposition: "",
    owner: terminal.owner,
    raw_rule_id: "",
    native_type: terminal.native_type,
    urn: terminal.urn,
    provenance: "",
    verification_state: null,
    readback_state: null,
    datahub_url: terminal.datahub_url,
    available: false
  };
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function isString(value: string | null): value is string {
  return value !== null;
}

export function dataHubPropertiesUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    url.pathname = `${url.pathname.replace(/\/+$/, "")}/Properties`;
    return url.toString();
  } catch {
    return null;
  }
}

function abortableDelay(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = globalThis.setTimeout(resolve, milliseconds);
    signal.addEventListener(
      "abort",
      () => {
        globalThis.clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true }
    );
  });
}

function isAbortError(error: unknown): boolean {
  return (
    error instanceof DOMException
      ? error.name === "AbortError"
      : error instanceof Error && error.name === "AbortError"
  );
}
