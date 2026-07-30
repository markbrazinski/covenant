import type {
  ExtractionRecord,
  MatchDetail,
  ProgressEvent,
  RegisteredAgreement,
  VerificationFailure,
} from "../adapter/AnalysisApi";
import type { SelectedDocument } from "../record/AnalysisComponents";

export type AnalysisStage =
  | "LANDING"
  | "MATCHING"
  | "EXTRACTING"
  | "VERIFIED"
  | "REJECTED"
  | "NO_MATCH"
  | "ERROR";

export interface AnalysisState {
  stage: AnalysisStage;
  document: SelectedDocument | null;
  matchId: string | null;
  matchEvents: ProgressEvent[];
  extractionEvents: ProgressEvent[];
  match: MatchDetail | null;
  extraction: ExtractionRecord | null;
  registeredCount: number | null;
  identifiedVendor: string | null;
  identifiedObligation: string | null;
  failures: VerificationFailure[];
  errorMessage: string | null;
  errorContext: "registry" | "match" | "extraction" | null;
  warning: string | null;
}

export type AnalysisAction =
  | { type: "REGISTRY_LOADED"; count: number }
  | { type: "DOCUMENT_SELECTED"; document: SelectedDocument }
  | { type: "MATCH_ACCEPTED"; matchId: string }
  | { type: "MATCH_EVENT"; event: ProgressEvent }
  | { type: "MATCH_DETAIL"; detail: MatchDetail }
  | { type: "EXTRACTION_EVENT"; event: ProgressEvent }
  | { type: "EXTRACTION_RESPONSE"; record: ExtractionRecord }
  | { type: "WARNING"; message: string | null }
  | {
      type: "ERROR";
      message: string;
      context: "registry" | "match" | "extraction";
    }
  | { type: "RESTORE"; detail: MatchDetail }
  | { type: "RETRY_EXTRACTION" }
  | { type: "RESET" };

export const initialAnalysisState: AnalysisState = {
  stage: "LANDING",
  document: null,
  matchId: null,
  matchEvents: [],
  extractionEvents: [],
  match: null,
  extraction: null,
  registeredCount: null,
  identifiedVendor: null,
  identifiedObligation: null,
  failures: [],
  errorMessage: null,
  errorContext: null,
  warning: null,
};

function appendUnique(
  values: ProgressEvent[],
  event: ProgressEvent,
): ProgressEvent[] {
  return values.some((item) => item.sequence === event.sequence)
    ? values
    : [...values, event];
}

export function analysisReducer(
  state: AnalysisState,
  action: AnalysisAction,
): AnalysisState {
  switch (action.type) {
    case "REGISTRY_LOADED":
      return { ...state, registeredCount: action.count };
    case "DOCUMENT_SELECTED":
      return {
        ...initialAnalysisState,
        registeredCount: state.registeredCount,
        document: action.document,
        stage: "MATCHING",
      };
    case "MATCH_ACCEPTED":
      return { ...state, matchId: action.matchId };
    case "MATCH_DETAIL":
      return {
        ...state,
        match: action.detail,
        identifiedVendor:
          action.detail.result?.extracted_vendor_name ??
          state.identifiedVendor,
        identifiedObligation:
          action.detail.result?.extracted_obligation_id ??
          state.identifiedObligation,
      };
    case "MATCH_EVENT": {
      const event = action.event;
      const identifiedVendor =
        typeof event.vendor_name_sent === "string"
          ? event.vendor_name_sent
          : state.identifiedVendor;
      const identifiedObligation =
        typeof event.obligation_id_sent === "string"
          ? event.obligation_id_sent
          : state.identifiedObligation;
      if (event.phase === "MATCH_NOT_FOUND") {
        return {
          ...state,
          stage: "NO_MATCH",
          matchEvents: appendUnique(state.matchEvents, event),
          identifiedVendor,
          identifiedObligation,
          warning: null,
        };
      }
      if (event.phase === "MATCH_REJECTED") {
        return {
          ...state,
          stage: "ERROR",
          matchEvents: appendUnique(state.matchEvents, event),
          identifiedVendor,
          identifiedObligation,
          errorMessage: failureMessage(event),
          errorContext: "match",
          warning: null,
        };
      }
      return {
        ...state,
        stage:
          event.phase === "MATCH_VERIFIED" ? "EXTRACTING" : state.stage,
        matchEvents: appendUnique(state.matchEvents, event),
        identifiedVendor,
        identifiedObligation,
        warning: null,
      };
    }
    case "EXTRACTION_EVENT": {
      const event = action.event;
      const events = appendUnique(state.extractionEvents, event);
      if (event.phase === "CANDIDATE_READY") {
        return {
          ...state,
          stage: "VERIFIED",
          extractionEvents: events,
          warning: null,
        };
      }
      if (event.phase === "EXTRACTION_REJECTED") {
        return {
          ...state,
          stage: "REJECTED",
          extractionEvents: events,
          failures: verificationFailures(event),
          warning: null,
        };
      }
      if (event.phase === "EXTRACTION_FAILED") {
        return {
          ...state,
          stage: "ERROR",
          extractionEvents: events,
          errorMessage: extractionFailureMessage(event),
          errorContext: "extraction",
          warning: null,
        };
      }
      return {
        ...state,
        stage: "EXTRACTING",
        extractionEvents: events,
        warning: null,
      };
    }
    case "EXTRACTION_RESPONSE":
      return {
        ...state,
        extraction: action.record,
        failures: action.record.verification.failures ?? state.failures,
      };
    case "WARNING":
      return { ...state, warning: action.message };
    case "ERROR":
      return {
        ...state,
        stage: "ERROR",
        errorMessage: action.message,
        errorContext: action.context,
        warning: null,
      };
    case "RESTORE":
      return restoreAnalysis(state.registeredCount, action.detail);
    case "RETRY_EXTRACTION":
      return {
        ...state,
        stage: "EXTRACTING",
        extractionEvents: [],
        extraction: null,
        failures: [],
        errorMessage: null,
        errorContext: null,
        warning: null,
      };
    case "RESET":
      return {
        ...initialAnalysisState,
        registeredCount: state.registeredCount,
      };
  }
}

function restoreAnalysis(
  registeredCount: number | null,
  detail: MatchDetail,
): AnalysisState {
  const extractionEvents = detail.extraction_events ?? [];
  const extractionPhase = detail.extraction_phase;
  let stage: AnalysisStage = "MATCHING";
  if (extractionPhase === "CANDIDATE_READY" || detail.change_id) {
    stage = "VERIFIED";
  } else if (extractionPhase === "EXTRACTION_REJECTED") {
    stage = "REJECTED";
  } else if (extractionPhase === "EXTRACTION_FAILED") {
    stage = "ERROR";
  } else if (extractionPhase) {
    stage = "EXTRACTING";
  } else if (detail.phase === "MATCH_VERIFIED") {
    stage = "EXTRACTING";
  } else if (detail.phase === "MATCH_NOT_FOUND") {
    stage = "NO_MATCH";
  } else if (detail.phase === "MATCH_REJECTED") {
    stage = "ERROR";
  }
  const terminal = extractionEvents[extractionEvents.length - 1];
  return {
    ...initialAnalysisState,
    registeredCount,
    stage,
    matchId: detail.match_id,
    matchEvents: detail.events,
    extractionEvents,
    match: detail,
    identifiedVendor: detail.result?.extracted_vendor_name ?? null,
    identifiedObligation:
      detail.result?.extracted_obligation_id ?? null,
    failures:
      terminal?.phase === "EXTRACTION_REJECTED"
        ? verificationFailures(terminal)
        : [],
    errorMessage:
      terminal?.phase === "EXTRACTION_FAILED"
        ? extractionFailureMessage(terminal)
        : detail.phase === "MATCH_REJECTED"
          ? failureMessage(detail.events[detail.events.length - 1] ?? {})
          : null,
    errorContext:
      terminal?.phase === "EXTRACTION_FAILED"
        ? "extraction"
        : detail.phase === "MATCH_REJECTED"
          ? "match"
          : null,
    warning: null,
  };
}

function verificationFailures(event: ProgressEvent): VerificationFailure[] {
  return Array.isArray(event.failures)
    ? (event.failures as VerificationFailure[])
    : [];
}

function failureMessage(event: ProgressEvent): string {
  const failures = verificationFailures(event);
  return (
    failures[0]?.message ??
    "Agreement matching was rejected by deterministic verification."
  );
}

function extractionFailureMessage(event: ProgressEvent): string {
  switch (event.failure_category) {
    case "TIMEOUT":
      return "Bedrock did not respond within 30 seconds.";
    case "MODEL_UNAVAILABLE":
      return "The configured Bedrock model is temporarily unavailable.";
    case "SOURCE_UNAVAILABLE":
      return "The governed source document is no longer available.";
    default:
      return "Extraction could not complete; no candidate was produced.";
  }
}

export function matchedAgreement(
  state: AnalysisState,
): RegisteredAgreement | null {
  return state.match?.result?.tool_call.tool_result_match ?? null;
}

export function hasPhase(events: ProgressEvent[], phase: string): boolean {
  return events.some((event) => event.phase === phase);
}
