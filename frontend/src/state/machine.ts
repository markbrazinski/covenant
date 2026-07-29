/**
 * Central application state machine (pure, framework-free, unit-testable).
 *
 * One explicit status models the whole authorize → analyze → inspect → record →
 * verify journey plus the DataHub-unavailable and partial-write failures. The
 * machine holds no fixture data — it reacts to adapter events and to user intent.
 * Wall-clock timers are NEVER the source of truth here; only adapter events
 * (RUN_PROGRESS / REC_PROGRESS / *_ERROR) advance analysis and recording status.
 */
import type {
  RunProgressDTO,
  RecordingProgressDTO,
  ErrorProjectionDTO
} from "../adapter/contracts";
import type { LifecyclePhase } from "../types/domain";

export type Status =
  | "awaiting_activation" // A — reviewed change, no affected set
  | "activating" // authorization fired, run not yet reporting
  | "resolving_impact" // API-observed ACTIVE / RESOLVING_IMPACT
  | "analysis_complete" // B — responses proposed, not recorded
  | "recording" // recording proposed responses in DataHub
  | "verifying_readbacks" // verifying DataHub readbacks
  | "recorded_verified" // C — recorded & verified
  | "datahub_unavailable" // DataHub/MCP failure — affected set cleared
  | "partial_write"; // some recorded/verified, some incomplete — safe retry

export interface MachineState {
  status: Status;
  runProgress: RunProgressDTO | null;
  recProgress: RecordingProgressDTO | null;
  error: ErrorProjectionDTO | null;
  selectedTerminalId: string | null;
}

export type Event =
  | { type: "ACTIVATE" }
  | { type: "RUN_PROGRESS"; p: RunProgressDTO }
  | { type: "RUN_ERROR"; e: ErrorProjectionDTO }
  | { type: "RECORD" }
  | { type: "REC_PROGRESS"; p: RecordingProgressDTO }
  | { type: "REC_ERROR"; e: ErrorProjectionDTO }
  | { type: "SELECT"; id: string | null }
  | { type: "RETRY" }
  | { type: "RESET" };

export const initialState: MachineState = {
  status: "awaiting_activation",
  runProgress: null,
  recProgress: null,
  error: null,
  selectedTerminalId: null
};

const RUN_PHASE_TO_STATUS: Record<RunProgressDTO["phase"], Status> = {
  resolving_impact: "resolving_impact",
  complete: "analysis_complete"
};

export function reducer(s: MachineState, ev: Event): MachineState {
  switch (ev.type) {
    case "ACTIVATE":
      if (s.status !== "awaiting_activation") return s;
      return { ...initialState, status: "activating" };

    case "RUN_PROGRESS": {
      // ignore stray run events once we've left the analysis lifecycle
      if (isRecordingLifecycle(s.status) || s.status === "datahub_unavailable") return s;
      const status = RUN_PHASE_TO_STATUS[ev.p.phase];
      return { ...s, status, runProgress: ev.p, error: null };
    }

    case "RUN_ERROR":
      // DataHub/MCP failure clears the affected set: no plan, no selection.
      return {
        ...initialState,
        status: "datahub_unavailable",
        error: ev.e
      };

    case "SELECT":
      // selection is only meaningful once an affected set exists
      if (!hasAffectedSet(s.status)) return s;
      return { ...s, selectedTerminalId: ev.id };

    case "RECORD":
      if (s.status !== "analysis_complete" && s.status !== "partial_write") return s;
      return { ...s, status: "recording", error: null };

    case "REC_PROGRESS": {
      let status: Status = s.status;
      if (ev.p.phase === "recording") status = "recording";
      else if (ev.p.phase === "verifying_readbacks") status = "verifying_readbacks";
      else if (ev.p.phase === "reconciled") status = "recorded_verified";
      else if (ev.p.phase === "partial") status = "partial_write";
      return { ...s, status, recProgress: ev.p };
    }

    case "REC_ERROR":
      return { ...s, status: "partial_write", error: ev.e };

    case "RETRY":
      if (s.status === "datahub_unavailable") return { ...initialState, status: "activating" };
      if (s.status === "partial_write") return { ...s, status: "recording", error: null };
      return s;

    case "RESET":
      return { ...initialState };

    default:
      return s;
  }
}

// ---- selectors --------------------------------------------------------------

export function isRecordingLifecycle(status: Status): boolean {
  return (
    status === "recording" ||
    status === "verifying_readbacks" ||
    status === "recorded_verified" ||
    status === "partial_write"
  );
}

/** True once DataHub has derived an affected set that the user can inspect. */
export function hasAffectedSet(status: Status): boolean {
  return (
    status === "analysis_complete" ||
    isRecordingLifecycle(status)
  );
}

export function isAnalyzing(status: Status): boolean {
  return (
    status === "activating" ||
    status === "resolving_impact"
  );
}

/** Global lifecycle phase for the locked frames (A/B/C). */
export function globalPhase(status: Status): LifecyclePhase {
  if (status === "recorded_verified") return "verified";
  return "proposed";
}

/** Per-terminal phase during the recording/partial transitional states. */
export function phaseForTerminal(s: MachineState, id: string): LifecyclePhase {
  if (s.status === "recorded_verified") return "verified";
  const rp = s.recProgress;
  if (rp) {
    if (rp.verified_ids.includes(id)) return "verified";
    if (rp.recorded_ids.includes(id)) return "recorded";
  }
  return "proposed";
}

/** Human-readable label for the current analysis phase (for the live banner). */
export function analysisTitle(status: Status): string {
  switch (status) {
    case "activating":
      return "Authorizing impact analysis";
    case "resolving_impact":
      return "Resolving impact through DataHub";
    default:
      return "";
  }
}
