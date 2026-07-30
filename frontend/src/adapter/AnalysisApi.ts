export interface RegisteredAgreement {
  vendor_id: string;
  vendor_name: string;
  obligation_id: string;
  current_version: string;
  effective_date: string;
  prior_document_path: string;
}

export interface ProgressEvent {
  sequence: number;
  phase: string;
  [key: string]: unknown;
}

export interface MatchDetail {
  match_id: string;
  phase: string;
  events: ProgressEvent[];
  result: {
    extracted_vendor_name: string;
    extracted_obligation_id: string;
    tool_call: {
      tool_result_status: string;
      tool_result_match: RegisteredAgreement | null;
    };
    match_metadata: {
      model_id: string;
    };
  } | null;
  verification: { status: string; failures?: VerificationFailure[] } | null;
  receipt: Record<string, unknown> | null;
  change_id: string | null;
  extraction_phase?: string | null;
  extraction_events?: ProgressEvent[];
}

export interface VerificationFailure {
  rule_id: string | null;
  check: string;
  message: string;
}

export interface ExtractionRecord {
  change_id: string | null;
  candidate: {
    candidate_delta_id?: string;
    lifecycle_state: string;
    rules: Array<{
      rule_id: string;
      citation?: { quote?: string };
    }>;
    extraction_metadata?: { model_id?: string };
    verification?: {
      status: string;
      failures?: VerificationFailure[];
    };
  };
  verification: {
    status: string;
    failures?: VerificationFailure[];
  };
  persisted: boolean;
}

interface ErrorProjection {
  code?: string;
  message?: string;
  retryable?: boolean;
}

export class AnalysisApiError extends Error {
  constructor(
    message: string,
    readonly code = "ANALYSIS_UNAVAILABLE",
    readonly retryable = false,
  ) {
    super(message);
  }
}

const MATCH_PHASES = [
  "MATCH_STARTED",
  "IDENTIFYING_VENDOR",
  "TOOL_CALLED",
  "TOOL_RETURNED",
  "MATCH_VERIFYING",
  "MATCH_VERIFIED",
  "MATCH_REJECTED",
  "MATCH_NOT_FOUND",
];

const EXTRACTION_PHASES = [
  "PREPARING_SOURCES",
  "EXTRACTING_BEDROCK",
  "MODEL_OUTPUT_RECEIVED",
  "VERIFYING_SCHEMA",
  "VERIFYING_CITATIONS_AND_RULES",
  "VERIFYING_CANDIDATE_CONSISTENCY",
  "VERIFICATION_COMPLETED",
  "CANDIDATE_READY",
  "EXTRACTION_REJECTED",
  "EXTRACTION_FAILED",
];

export class AnalysisApi {
  constructor(
    readonly baseUrl =
      import.meta.env.VITE_COVENANT_API_URL ?? "http://127.0.0.1:8000",
  ) {}

  async registered(): Promise<RegisteredAgreement[]> {
    return this.request("/api/agreements/registered");
  }

  async startMatch(file: File): Promise<{
    match_id: string;
    stream_url: string;
  }> {
    const body = new FormData();
    body.append("document", file, file.name);
    return this.request("/api/analyses/match", {
      method: "POST",
      body,
    });
  }

  async match(matchId: string): Promise<MatchDetail> {
    return this.request(`/api/analyses/${encodeURIComponent(matchId)}`);
  }

  async extract(matchId: string): Promise<ExtractionRecord> {
    return this.request(
      `/api/analyses/${encodeURIComponent(matchId)}/extract`,
      { method: "POST" },
    );
  }

  observeMatch(
    matchId: string,
    onEvent: (event: ProgressEvent) => void,
    onDisconnect: () => void,
  ): () => void {
    return this.observe(
      `/api/analyses/${encodeURIComponent(matchId)}/events`,
      MATCH_PHASES,
      onEvent,
      onDisconnect,
    );
  }

  observeExtraction(
    matchId: string,
    onEvent: (event: ProgressEvent) => void,
    onDisconnect: () => void,
  ): () => void {
    return this.observe(
      `/api/analyses/${encodeURIComponent(matchId)}/extraction-events`,
      EXTRACTION_PHASES,
      onEvent,
      onDisconnect,
    );
  }

  private observe(
    path: string,
    phases: string[],
    onEvent: (event: ProgressEvent) => void,
    onDisconnect: () => void,
  ): () => void {
    const source = new EventSource(this.baseUrl + path);
    for (const phase of phases) {
      source.addEventListener(phase, (raw) => {
        try {
          onEvent(JSON.parse((raw as MessageEvent<string>).data));
        } catch {
          source.close();
          onDisconnect();
        }
      });
    }
    source.onerror = () => {
      source.close();
      onDisconnect();
    };
    return () => source.close();
  }

  private async request<T>(
    path: string,
    init?: RequestInit,
  ): Promise<T> {
    let response: Response;
    try {
      response = await fetch(this.baseUrl + path, init);
    } catch {
      throw new AnalysisApiError(
        "Covenant could not reach the local analysis service.",
        "SERVICE_UNAVAILABLE",
        true,
      );
    }
    if (!response.ok) {
      let error: ErrorProjection = {};
      try {
        error = (await response.json()) as ErrorProjection;
      } catch {
        // The safe fallback below intentionally ignores non-JSON bodies.
      }
      throw new AnalysisApiError(
        error.message ?? "The analysis request could not complete.",
        error.code,
        Boolean(error.retryable),
      );
    }
    return (await response.json()) as T;
  }
}
