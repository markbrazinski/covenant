import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
} from "react";

import {
  AnalysisApi,
  AnalysisApiError,
  type MatchDetail,
  type ProgressEvent,
  type VerificationFailure,
} from "../adapter/AnalysisApi";
import {
  analysisReducer,
  hasPhase,
  initialAnalysisState,
  matchedAgreement,
  type AnalysisStage,
} from "../state/analysisMachine";
import {
  AgentActivityPanel,
  AnalysisButton,
  AnalysisCard,
  AnalysisField,
  AnalysisNotice,
  AnalysisShell,
  AnalysisWorkspaceLayout,
  DocumentSlot,
  MatchedAgreementCard,
  PhaseList,
  PhaseRow,
  ReceiptCard,
  type AnalysisStatusKind,
  type ProgressVisualState,
  type SelectedDocument,
} from "./AnalysisComponents";

const MATCH_TERMINALS = new Set([
  "MATCH_VERIFIED",
  "MATCH_REJECTED",
  "MATCH_NOT_FOUND",
]);
const EXTRACTION_TERMINALS = new Set([
  "CANDIDATE_READY",
  "EXTRACTION_REJECTED",
  "EXTRACTION_FAILED",
]);

export function AnalysisWorkspace({
  routedMatchId,
  navigate,
}: {
  routedMatchId?: string;
  navigate: (path: string, replace?: boolean) => void;
}) {
  const api = useMemo(() => new AnalysisApi(), []);
  const [state, dispatch] = useReducer(
    analysisReducer,
    initialAnalysisState,
  );
  const stateRef = useRef(state);
  const matchCloseRef = useRef<(() => void) | null>(null);
  const extractionCloseRef = useRef<(() => void) | null>(null);
  const extractionStartedRef = useRef(false);
  const restoreStartedRef = useRef(false);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const disconnectError = useCallback((kind: "match" | "extraction") => {
    const current = stateRef.current.stage;
    if (
      (kind === "match" && current !== "MATCHING") ||
      (kind === "extraction" && current !== "EXTRACTING")
    ) {
      return;
    }
    dispatch({
      type: "ERROR",
      context: kind,
      message:
        kind === "match"
          ? "The match progress connection closed before a result was verified."
          : "The extraction progress connection closed before verification completed.",
    });
  }, []);

  const startExtraction = useCallback(
    async (matchId: string, knownDetail?: MatchDetail) => {
      if (extractionStartedRef.current) return;
      extractionStartedRef.current = true;
      dispatch({ type: "RETRY_EXTRACTION" });
      try {
        const detail = knownDetail ?? (await api.match(matchId));
        dispatch({ type: "MATCH_DETAIL", detail });
        extractionCloseRef.current?.();
        extractionCloseRef.current = api.observeExtraction(
          matchId,
          (event) => {
            dispatch({ type: "EXTRACTION_EVENT", event });
            if (EXTRACTION_TERMINALS.has(event.phase)) {
              extractionCloseRef.current?.();
              extractionCloseRef.current = null;
            }
          },
          () => disconnectError("extraction"),
        );
        const record = await api.extract(matchId);
        dispatch({ type: "EXTRACTION_RESPONSE", record });
      } catch (error) {
        if (
          !EXTRACTION_TERMINALS.has(
            stateRef.current.extractionEvents[
              stateRef.current.extractionEvents.length - 1
            ]?.phase ?? "",
          )
        ) {
          dispatch({
            type: "ERROR",
            context: "extraction",
            message: safeError(error),
          });
        }
      }
    },
    [api, disconnectError],
  );

  const observeMatch = useCallback(
    (matchId: string) => {
      matchCloseRef.current?.();
      matchCloseRef.current = api.observeMatch(
        matchId,
        (event) => {
          dispatch({ type: "MATCH_EVENT", event });
          if (!MATCH_TERMINALS.has(event.phase)) return;
          matchCloseRef.current?.();
          matchCloseRef.current = null;
          void api
            .match(matchId)
            .then((detail) => {
              dispatch({ type: "MATCH_DETAIL", detail });
              if (event.phase === "MATCH_VERIFIED") {
                void startExtraction(matchId, detail);
              }
            })
            .catch((error) =>
              dispatch({
                type: "ERROR",
                context: "match",
                message: safeError(error),
              }),
            );
        },
        () => disconnectError("match"),
      );
    },
    [api, disconnectError, startExtraction],
  );

  useEffect(() => {
    void api
      .registered()
      .then((agreements) =>
        dispatch({ type: "REGISTRY_LOADED", count: agreements.length }),
      )
      .catch((error) =>
        dispatch({
          type: "ERROR",
          context: "registry",
          message: safeError(error),
        }),
      );
  }, [api]);

  useEffect(() => {
    if (!routedMatchId || restoreStartedRef.current) return;
    restoreStartedRef.current = true;
    void api
      .match(routedMatchId)
      .then((detail) => {
        dispatch({ type: "RESTORE", detail });
        if (!MATCH_TERMINALS.has(detail.phase)) {
          observeMatch(routedMatchId);
          return;
        }
        if (detail.phase !== "MATCH_VERIFIED") return;
        if (
          detail.extraction_phase &&
          !EXTRACTION_TERMINALS.has(detail.extraction_phase)
        ) {
          extractionStartedRef.current = true;
          extractionCloseRef.current = api.observeExtraction(
            routedMatchId,
            (event) => {
              dispatch({ type: "EXTRACTION_EVENT", event });
              if (EXTRACTION_TERMINALS.has(event.phase)) {
                extractionCloseRef.current?.();
                extractionCloseRef.current = null;
              }
            },
            () => disconnectError("extraction"),
          );
        } else if (!detail.extraction_phase && !detail.change_id) {
          void startExtraction(routedMatchId, detail);
        }
      })
      .catch((error) =>
        dispatch({
          type: "ERROR",
          context: "match",
          message: safeError(error),
        }),
      );
  }, [
    api,
    disconnectError,
    observeMatch,
    routedMatchId,
    startExtraction,
  ]);

  useEffect(
    () => () => {
      matchCloseRef.current?.();
      extractionCloseRef.current?.();
    },
    [],
  );

  useEffect(() => {
    if (state.stage !== "MATCHING" && state.stage !== "EXTRACTING") return;
    dispatch({ type: "WARNING", message: null });
    const handle = window.setTimeout(() => {
      dispatch({
        type: "WARNING",
        message:
          state.stage === "MATCHING"
            ? "Still waiting for the next verified match event."
            : "Still waiting for the next extraction checkpoint.",
      });
    }, 10_000);
    return () => window.clearTimeout(handle);
  }, [
    state.stage,
    state.matchEvents.length,
    state.extractionEvents.length,
  ]);

  const selectDocument = useCallback(
    async (file: File) => {
      const document = await describeDocument(file);
      dispatch({ type: "DOCUMENT_SELECTED", document });
      extractionStartedRef.current = false;
      try {
        const accepted = await api.startMatch(file);
        dispatch({
          type: "MATCH_ACCEPTED",
          matchId: accepted.match_id,
        });
        // This route change belongs to the current mounted flow. Do not treat it
        // as a cold deep-link restore and open a duplicate SSE subscription.
        restoreStartedRef.current = true;
        navigate(`/analyze/${encodeURIComponent(accepted.match_id)}`);
        observeMatch(accepted.match_id);
      } catch (error) {
        dispatch({
          type: "ERROR",
          context: "match",
          message: safeError(error),
        });
      }
    },
    [api, navigate, observeMatch],
  );

  const reset = useCallback(() => {
    matchCloseRef.current?.();
    extractionCloseRef.current?.();
    matchCloseRef.current = null;
    extractionCloseRef.current = null;
    extractionStartedRef.current = false;
    restoreStartedRef.current = false;
    dispatch({ type: "RESET" });
    navigate("/analyze");
  }, [navigate]);

  const retryExtraction = useCallback(() => {
    if (!state.matchId) return;
    extractionStartedRef.current = false;
    void startExtraction(state.matchId);
  }, [startExtraction, state.matchId]);

  const status = statusFor(state.stage, state.errorContext);
  const agreement = matchedAgreement(state);
  const changeId =
    state.extraction?.change_id ?? state.match?.change_id ?? null;

  return (
    <AnalysisShell status={status}>
      <AnalysisWorkspaceLayout
        main={
          <div>
            <h1 className="serif analysis-page-title">
              Analyze a governed agreement change
            </h1>
            <p className="analysis-page-intro">
              Upload a new version of a data-use agreement. Covenant identifies
              its governed obligation, retrieves the in-effect prior version,
              and extracts an evidence-bound candidate for human review.
            </p>
            <p className="mono analysis-registry-count">
              {state.registeredCount === null
                ? "Checking the governed-agreement registry…"
                : `Covenant currently governs ${state.registeredCount} ${
                    state.registeredCount === 1 ? "agreement" : "agreements"
                  }.`}
            </p>

            {state.document ? (
              <DocumentSlot
                document={state.document}
                disabled={
                  state.stage === "MATCHING" ||
                  state.stage === "EXTRACTING"
                }
                onSelect={selectDocument}
              />
            ) : routedMatchId ? (
              <AnalysisCard>
                <div className="mono analysis-section-label">
                  Candidate version · retained by active analysis
                </div>
                <p className="analysis-retained-copy">
                  File metadata is unavailable after navigation. Covenant is
                  reading the server-held document for {routedMatchId}.
                </p>
              </AnalysisCard>
            ) : (
              <DocumentSlot document={null} onSelect={selectDocument} />
            )}

            {state.stage !== "LANDING" && (
              <MatchingPhases
                stage={state.stage}
                events={state.matchEvents}
              />
            )}

            {agreement && (
              <>
                <div className="mono analysis-amends" aria-hidden="true">
                  ↑ amends
                </div>
                <MatchedAgreementCard
                  vendor={agreement.vendor_name}
                  obligationId={agreement.obligation_id}
                  currentVersion={agreement.current_version}
                  effectiveDate={agreement.effective_date.slice(0, 10)}
                  subdued={state.stage === "EXTRACTING"}
                />
              </>
            )}

            {[
              "EXTRACTING",
              "VERIFIED",
              "REJECTED",
            ].includes(state.stage) && (
              <ExtractionPhases
                stage={state.stage}
                events={state.extractionEvents}
              />
            )}

            {state.warning && (
              <div className="analysis-warning" role="status">
                {state.warning}
              </div>
            )}

            <TerminalState
              stage={state.stage}
              failures={state.failures}
              errorMessage={state.errorMessage}
              vendor={state.identifiedVendor}
              obligation={state.identifiedObligation}
              candidateId={
                state.extraction?.candidate.candidate_delta_id ?? null
              }
              modelId={
                state.extraction?.candidate.extraction_metadata?.model_id ??
                state.match?.result?.match_metadata.model_id ??
                null
              }
              onReset={reset}
              onRetryExtraction={retryExtraction}
              canRetryExtraction={Boolean(
                state.matchId &&
                agreement &&
                state.extractionEvents.length > 0
              )}
              onContinue={() => {
                navigate(
                  changeId
                    ? `/changes/${encodeURIComponent(changeId)}`
                    : "/changes",
                );
                window.scrollTo({ top: 0, left: 0, behavior: "auto" });
              }}
            />
          </div>
        }
        activity={
          <Activity
            stage={state.stage}
            matchEvents={state.matchEvents}
            extractionEvents={state.extractionEvents}
            vendor={state.identifiedVendor}
            obligation={state.identifiedObligation}
            agreement={agreement}
            failures={state.failures}
            errorMessage={state.errorMessage}
          />
        }
      />
    </AnalysisShell>
  );
}

function MatchingPhases({
  stage,
  events,
}: {
  stage: AnalysisStage;
  events: ProgressEvent[];
}) {
  const terminal = [
    "EXTRACTING",
    "VERIFIED",
    "REJECTED",
  ].includes(stage);
  const failed = stage === "NO_MATCH" || stage === "ERROR";
  const toolCalled = hasPhase(events, "TOOL_CALLED");
  return (
    <PhaseList label="Matching to registered agreement">
      <PhaseRow
        label="Identifying vendor and obligation"
        state={
          toolCalled || terminal
            ? "complete"
            : failed
              ? "failed"
              : "active"
        }
      />
      <PhaseRow
        label="Retrieving and verifying prior version from registry"
        state={
          terminal
            ? "complete"
            : failed
              ? "failed"
              : toolCalled
                ? "active"
                : "pending"
        }
      />
    </PhaseList>
  );
}

const EXTRACTION_STEPS = [
  { label: "Preparing sources", phase: "PREPARING_SOURCES" },
  { label: "Extracting via Bedrock", phase: "EXTRACTING_BEDROCK" },
  { label: "Verifying schema", phase: "VERIFYING_SCHEMA" },
  {
    label: "Verifying citations and rule types",
    phase: "VERIFYING_CITATIONS_AND_RULES",
  },
  {
    label: "Verifying candidate consistency",
    phase: "VERIFYING_CANDIDATE_CONSISTENCY",
  },
  { label: "Candidate ready", phase: "VERIFICATION_COMPLETED" },
] as const;

function ExtractionPhases({
  stage,
  events,
}: {
  stage: AnalysisStage;
  events: ProgressEvent[];
}) {
  const phases = events.map((event) => event.phase);
  const terminal =
    stage === "VERIFIED" || stage === "REJECTED";
  const terminalFailed = stage === "REJECTED";
  return (
    <PhaseList label="Extraction & deterministic verification">
      {EXTRACTION_STEPS.map((step, index) => {
        const ownIndex = phases.indexOf(step.phase);
        const later = EXTRACTION_STEPS.slice(index + 1).some((item) =>
          phases.includes(item.phase),
        );
        let visual: ProgressVisualState = "pending";
        if (stage === "VERIFIED" || later) visual = "complete";
        else if (ownIndex >= 0) visual = "active";
        if (
          terminalFailed &&
          (index === EXTRACTION_STEPS.length - 1 || ownIndex >= 0) &&
          !later
        ) {
          visual = "failed";
        }
        return (
          <PhaseRow
            key={step.phase}
            label={step.label}
            state={visual}
          />
        );
      })}
      {terminal && <span className="vh">Extraction terminal state reached.</span>}
    </PhaseList>
  );
}

function Activity({
  stage,
  matchEvents,
  extractionEvents,
  vendor,
  obligation,
  agreement,
  failures,
  errorMessage,
}: {
  stage: AnalysisStage;
  matchEvents: ProgressEvent[];
  extractionEvents: ProgressEvent[];
  vendor: string | null;
  obligation: string | null;
  agreement: ReturnType<typeof matchedAgreement>;
  failures: VerificationFailure[];
  errorMessage: string | null;
}) {
  const toolCalled = hasPhase(matchEvents, "TOOL_CALLED");
  const toolReturned = hasPhase(matchEvents, "TOOL_RETURNED");
  const matchFailed = stage === "NO_MATCH" || (
    stage === "ERROR" && extractionEvents.length === 0
  );
  const extracting = hasPhase(extractionEvents, "EXTRACTING_BEDROCK");
  const extractionDone = stage === "VERIFIED";
  const extractionFailed = stage === "REJECTED" || (
    stage === "ERROR" && extractionEvents.length > 0
  );
  if (!toolCalled && !extracting) return <AgentActivityPanel />;
  return (
    <AgentActivityPanel>
      {toolCalled && (
        <ReceiptCard
          label="Registry lookup"
          state={matchFailed ? "failed" : toolReturned ? "complete" : "active"}
          call={`lookup_governed_agreement(${vendor ?? "identified vendor"}, ${
            obligation ?? "identified obligation"
          })`}
          result={
            matchFailed
              ? stage === "NO_MATCH"
                ? "→ NOT_FOUND"
                : `→ ${errorMessage ?? "Rejected"}`
              : toolReturned
                ? `→ ${agreement?.vendor_name ?? vendor ?? "MATCH"} · ${
                    agreement?.current_version ?? ""
                  } · effective ${
                    agreement?.effective_date.slice(0, 10) ?? ""
                  }`
                : "awaiting response…"
          }
        />
      )}
      {extracting && (
        <ReceiptCard
          label="Extraction & verification"
          state={
            extractionDone
              ? "complete"
              : extractionFailed
                ? "failed"
                : "active"
          }
          call="POST /analyses/{match_id}/extract"
          result={
            extractionDone
              ? "→ 4 rules extracted · 4 citations verified"
              : extractionFailed
                ? `→ ${
                    failures[0]
                      ? `${failures[0].rule_id ?? "candidate"} · ${
                          failures[0].check
                        }`
                      : errorMessage ?? "Extraction unavailable"
                  }`
                : "awaiting completion…"
          }
        />
      )}
    </AgentActivityPanel>
  );
}

function TerminalState({
  stage,
  failures,
  errorMessage,
  vendor,
  obligation,
  candidateId,
  modelId,
  onReset,
  onRetryExtraction,
  canRetryExtraction,
  onContinue,
}: {
  stage: AnalysisStage;
  failures: VerificationFailure[];
  errorMessage: string | null;
  vendor: string | null;
  obligation: string | null;
  candidateId: string | null;
  modelId: string | null;
  onReset: () => void;
  onRetryExtraction: () => void;
  canRetryExtraction: boolean;
  onContinue: () => void;
}) {
  if (stage === "VERIFIED") {
    return (
      <AnalysisNotice
        kind="verified"
        title="Candidate verified and ready for review"
        body="4 rules extracted from Atlas Signals v3 → v4. 4 citations verified against source."
      >
        <div className="analysis-summary">
          <AnalysisField
            label="Candidate ID"
            value={candidateId ?? "available in Changes"}
          />
          <AnalysisField
            label="Extraction model"
            value={conciseModel(modelId)}
          />
        </div>
        <div className="analysis-actions">
          <AnalysisButton onClick={onContinue}>
            Continue to review
          </AnalysisButton>
        </div>
      </AnalysisNotice>
    );
  }
  if (stage === "REJECTED") {
    return (
      <AnalysisNotice
        kind="rejected"
        title="Candidate rejected by deterministic verification"
        body="No reviewable candidate was recorded."
      >
        <FailureList failures={failures} />
        <div className="analysis-actions">
          <AnalysisButton kind="ink" onClick={onReset}>
            Load a different document
          </AnalysisButton>
        </div>
      </AnalysisNotice>
    );
  }
  if (stage === "NO_MATCH") {
    return (
      <AnalysisNotice
        kind="no-match"
        title="Agreement not recognized"
        body={`${vendor ?? "The identified vendor"} · ${
          obligation ?? "identified obligation"
        } is not registered as a governed agreement.`}
      >
        <div className="analysis-actions">
          <AnalysisButton kind="ink" onClick={onReset}>
            Try another document
          </AnalysisButton>
        </div>
      </AnalysisNotice>
    );
  }
  if (stage === "ERROR") {
    return (
      <AnalysisNotice
        kind="error"
        title="Analysis could not complete"
        body={errorMessage ?? "No candidate was produced."}
      >
        <div className="analysis-actions">
          {canRetryExtraction && (
            <AnalysisButton kind="ink" onClick={onRetryExtraction}>
              Retry extraction
            </AnalysisButton>
          )}
          <AnalysisButton kind="link" onClick={onReset}>
            Load a different document
          </AnalysisButton>
        </div>
      </AnalysisNotice>
    );
  }
  return null;
}

function FailureList({ failures }: { failures: VerificationFailure[] }) {
  return (
    <ul className="analysis-failure-list">
      {failures.map((failure, index) => (
        <li key={`${failure.rule_id}-${failure.check}-${index}`}>
          <span className="mono">
            {failure.rule_id ?? "candidate"} · {failure.check}
          </span>
          <span>{failure.message}</span>
        </li>
      ))}
    </ul>
  );
}

function statusFor(
  stage: AnalysisStage,
  errorContext: "registry" | "match" | "extraction" | null,
): {
  kind: AnalysisStatusKind;
  label: string;
  announcement: string;
} {
  switch (stage) {
    case "LANDING":
      return {
        kind: "neutral",
        label: "Ready to analyze",
        announcement: "",
      };
    case "MATCHING":
      return {
        kind: "amber",
        label: "Matching agreement",
        announcement: "Matching agreement to the governed registry.",
      };
    case "EXTRACTING":
      return {
        kind: "amber",
        label: "Extracting via Bedrock",
        announcement: "Match verified. Extraction began automatically.",
      };
    case "VERIFIED":
      return {
        kind: "green",
        label: "Candidate verified",
        announcement: "Candidate verified and ready for human review.",
      };
    case "REJECTED":
      return {
        kind: "warn",
        label: "Verification failed",
        announcement: "Candidate rejected by deterministic verification.",
      };
    case "NO_MATCH":
      return {
        kind: "warn",
        label: "Agreement not recognized",
        announcement: "The identified agreement is not governed.",
      };
    case "ERROR":
      return {
        kind: "warn",
        label:
          errorContext === "extraction"
            ? "Extraction unavailable"
            : errorContext === "match"
              ? "Match unavailable"
              : "Analysis unavailable",
        announcement: "Analysis could not complete.",
      };
  }
}

async function describeDocument(file: File): Promise<SelectedDocument> {
  let hash = "unavailable";
  try {
    const digest = await crypto.subtle.digest(
      "SHA-256",
      await file.arrayBuffer(),
    );
    hash =
      [...new Uint8Array(digest)]
        .map((value) => value.toString(16).padStart(2, "0"))
        .join("")
        .slice(0, 12) + "…";
  } catch {
    // The UI remains truthful if Web Crypto is unavailable.
  }
  return {
    name: file.name,
    typeLabel: file.name.toLowerCase().endsWith(".pdf")
      ? "PDF"
      : file.name.toLowerCase().endsWith(".md")
        ? "MD"
        : "TXT",
    sizeLabel: formatBytes(file.size),
    sha256Label: hash,
  };
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function safeError(error: unknown): string {
  if (error instanceof AnalysisApiError) {
    switch (error.code) {
      case "SERVICE_UNAVAILABLE":
        return "Covenant could not reach the local analysis service.";
      case "MATCH_NOT_FOUND":
        return "The identified agreement is not registered as governed.";
      case "MATCH_SOURCE_UNAVAILABLE":
        return "The governed source document is no longer available.";
      case "VERIFIED_MATCH_REQUIRED":
        return "Extraction requires a verified agreement match.";
      case "EXTRACTION_FAILED":
        return "Extraction could not complete; no candidate was produced.";
      default:
        return "The analysis request could not complete safely.";
    }
  }
  return "The analysis request could not complete safely.";
}

function conciseModel(modelId: string | null): string {
  if (!modelId) return "not exposed";
  return modelId
    .replace(/^us\./, "")
    .replace(/-202[0-9]{5}-v1:0$/, "")
    .replace(/^anthropic\./, "bedrock/");
}
