import { describe, expect, it } from "vitest";

import type { MatchDetail, ProgressEvent } from "../adapter/AnalysisApi";
import {
  analysisReducer,
  initialAnalysisState,
  type AnalysisState,
} from "../state/analysisMachine";

const event = (
  sequence: number,
  phase: string,
  data: Record<string, unknown> = {},
): ProgressEvent => ({ sequence, phase, ...data });

const matched: MatchDetail = {
  match_id: "MATCH-real",
  phase: "MATCH_VERIFIED",
  events: [
    event(1, "MATCH_STARTED"),
    event(2, "MATCH_VERIFIED"),
  ],
  result: {
    extracted_vendor_name: "Atlas Signals",
    extracted_obligation_id: "ATLAS-LIC-004",
    tool_call: {
      tool_result_status: "MATCH",
      tool_result_match: {
        vendor_id: "atlas-signals",
        vendor_name: "Atlas Signals",
        obligation_id: "ATLAS-LIC-004",
        current_version: "v3",
        effective_date: "2025-07-01T00:00:00Z",
        prior_document_path: "fixtures/atlas_license_v3.md",
      },
    },
    match_metadata: { model_id: "test.model" },
  },
  verification: { status: "PASS" },
  receipt: {},
  change_id: null,
  extraction_phase: null,
  extraction_events: [],
};

function uploaded(): AnalysisState {
  return analysisReducer(initialAnalysisState, {
    type: "DOCUMENT_SELECTED",
    document: {
      name: "atlas_license_v4.pdf",
      typeLabel: "PDF",
      sizeLabel: "418 KB",
      sha256Label: "abc123…",
    },
  });
}

describe("Beat 0 analysis state machine", () => {
  it("enters matching only from an explicit document selection", () => {
    const state = uploaded();
    expect(state.stage).toBe("MATCHING");
    expect(state.document?.name).toBe("atlas_license_v4.pdf");
    expect(state.matchEvents).toEqual([]);
  });

  it("enters extraction only on MATCH_VERIFIED", () => {
    let state = uploaded();
    state = analysisReducer(state, {
      type: "MATCH_EVENT",
      event: event(1, "IDENTIFYING_VENDOR"),
    });
    expect(state.stage).toBe("MATCHING");
    state = analysisReducer(state, {
      type: "MATCH_EVENT",
      event: event(2, "MATCH_VERIFIED"),
    });
    expect(state.stage).toBe("EXTRACTING");
  });

  it("distinguishes a real not-found from a rejected match", () => {
    const noMatch = analysisReducer(uploaded(), {
      type: "MATCH_EVENT",
      event: event(2, "MATCH_NOT_FOUND", {
        vendor_name_sent: "Unknown Vendor",
      }),
    });
    expect(noMatch.stage).toBe("NO_MATCH");

    const rejected = analysisReducer(uploaded(), {
      type: "MATCH_EVENT",
      event: event(2, "MATCH_REJECTED", {
        failures: [
          {
            rule_id: null,
            check: "schema_validation",
            message: "Match evidence did not verify.",
          },
        ],
      }),
    });
    expect(rejected.stage).toBe("ERROR");
    expect(rejected.errorMessage).toBe("Match evidence did not verify.");
  });

  it("uses only terminal extraction events for terminal UI states", () => {
    let state = analysisReducer(uploaded(), {
      type: "MATCH_EVENT",
      event: event(1, "MATCH_VERIFIED"),
    });
    for (const [index, phase] of [
      "PREPARING_SOURCES",
      "EXTRACTING_BEDROCK",
      "VERIFYING_SCHEMA",
      "VERIFYING_CITATIONS_AND_RULES",
      "VERIFYING_CANDIDATE_CONSISTENCY",
      "VERIFICATION_COMPLETED",
    ].entries()) {
      state = analysisReducer(state, {
        type: "EXTRACTION_EVENT",
        event: event(index + 1, phase),
      });
      expect(state.stage).toBe("EXTRACTING");
    }
    state = analysisReducer(state, {
      type: "EXTRACTION_EVENT",
      event: event(7, "CANDIDATE_READY", {
        change_id: "CHANGE-real",
      }),
    });
    expect(state.stage).toBe("VERIFIED");
  });

  it("surfaces rejection evidence and safe timeout copy", () => {
    const rejected = analysisReducer(uploaded(), {
      type: "EXTRACTION_EVENT",
      event: event(8, "EXTRACTION_REJECTED", {
        failures: [
          {
            rule_id: "R-003",
            check: "citation_verification",
            message: "Citation was not found.",
          },
        ],
      }),
    });
    expect(rejected.stage).toBe("REJECTED");
    expect(rejected.failures[0]).toMatchObject({
      rule_id: "R-003",
      check: "citation_verification",
    });

    const timedOut = analysisReducer(uploaded(), {
      type: "EXTRACTION_EVENT",
      event: event(8, "EXTRACTION_FAILED", {
        failure_category: "TIMEOUT",
        message: "provider internals",
      }),
    });
    expect(timedOut.stage).toBe("ERROR");
    expect(timedOut.errorMessage).toBe(
      "Bedrock did not respond within 30 seconds.",
    );
    expect(timedOut.errorMessage).not.toContain("provider internals");
  });

  it("restores deep-linked terminal state from backend evidence", () => {
    const restored = analysisReducer(initialAnalysisState, {
      type: "RESTORE",
      detail: {
        ...matched,
        change_id: "CHANGE-real",
        extraction_phase: "CANDIDATE_READY",
        extraction_events: [event(8, "CANDIDATE_READY")],
      },
    });
    expect(restored.stage).toBe("VERIFIED");
    expect(restored.matchId).toBe("MATCH-real");
    expect(restored.identifiedVendor).toBe("Atlas Signals");
  });

  it("deduplicates re-delivered SSE sequence numbers", () => {
    const first = analysisReducer(uploaded(), {
      type: "MATCH_EVENT",
      event: event(1, "MATCH_STARTED"),
    });
    const repeated = analysisReducer(first, {
      type: "MATCH_EVENT",
      event: event(1, "MATCH_STARTED"),
    });
    expect(repeated.matchEvents).toHaveLength(1);
  });
});
