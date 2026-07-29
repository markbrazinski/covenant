import { describe, it, expect } from "vitest";
import { reducer, initialState, phaseForTerminal } from "../state/machine";
import type { MachineState } from "../state/machine";
import type { RunProgressDTO, RecordingProgressDTO } from "../adapter/contracts";

const run = (phase: RunProgressDTO["phase"]): RunProgressDTO => ({
  run_id: "r",
  phase,
  server_stage: phase === "complete" ? "IMPACT_READY" : "RESOLVING_IMPACT",
  server_message: phase === "complete" ? "ready" : "resolving",
  source_resolution_status: "ok",
  downstream_entity_count: 11,
  terminal_path_count: 5,
  tiers_resolved: 3,
  tiers_total: 3,
  terminals_revealed: 5
});

describe("machine", () => {
  it("starts awaiting activation with no affected set", () => {
    expect(initialState.status).toBe("awaiting_activation");
    expect(initialState.selectedTerminalId).toBeNull();
  });

  it("activation only fires from awaiting_activation", () => {
    const s = reducer(initialState, { type: "ACTIVATE" });
    expect(s.status).toBe("activating");
    // a second activate is a no-op
    expect(reducer(s, { type: "ACTIVATE" })).toBe(s);
  });

  it("progresses analysis without selecting a terminal at completion", () => {
    let s: MachineState = reducer(initialState, { type: "ACTIVATE" });
    s = reducer(s, { type: "RUN_PROGRESS", p: run("resolving_impact") });
    expect(s.status).toBe("resolving_impact");
    expect(s.selectedTerminalId).toBeNull(); // no selection before an affected set
    s = reducer(s, { type: "RUN_PROGRESS", p: run("complete") });
    expect(s.status).toBe("analysis_complete");
    expect(s.selectedTerminalId).toBeNull();
  });

  it("selection is ignored before an affected set exists", () => {
    const s = reducer(initialState, { type: "SELECT", id: "churn_model_a" });
    expect(s.selectedTerminalId).toBeNull();
  });

  it("datahub failure clears the affected set and selection", () => {
    let s: MachineState = reducer(initialState, { type: "ACTIVATE" });
    s = reducer(s, { type: "RUN_PROGRESS", p: run("complete") });
    s = reducer(s, {
      type: "RUN_ERROR",
      e: { code: "DATAHUB_UNAVAILABLE", title: "x", detail: "y", clears_affected_set: true }
    });
    expect(s.status).toBe("datahub_unavailable");
    expect(s.selectedTerminalId).toBeNull();
    expect(s.runProgress).toBeNull();
  });

  it("records then verifies to the recorded_verified climax", () => {
    let s: MachineState = reducer(initialState, { type: "ACTIVATE" });
    s = reducer(s, { type: "RUN_PROGRESS", p: run("complete") });
    s = reducer(s, { type: "RECORD" });
    expect(s.status).toBe("recording");
    const rec = (phase: RecordingProgressDTO["phase"]): RecordingProgressDTO => ({
      run_id: "r",
      phase,
      target_count: 5,
      recorded_count: 5,
      readback_verified_count: 5,
      recorded_ids: [],
      verified_ids: [],
      incomplete_ids: [],
      stable_replay: phase === "reconciled",
      entity_progress: []
    });
    s = reducer(s, { type: "REC_PROGRESS", p: rec("recording") });
    s = reducer(s, { type: "REC_PROGRESS", p: rec("verifying_readbacks") });
    expect(s.status).toBe("verifying_readbacks");
    s = reducer(s, { type: "REC_PROGRESS", p: rec("reconciled") });
    expect(s.status).toBe("recorded_verified");
  });

  it("partial write is retryable and preserves progress", () => {
    let s: MachineState = reducer(initialState, { type: "ACTIVATE" });
    s = reducer(s, { type: "RUN_PROGRESS", p: run("complete") });
    s = reducer(s, { type: "RECORD" });
    s = reducer(s, {
      type: "REC_PROGRESS",
      p: {
        run_id: "r",
        phase: "partial",
        target_count: 5,
        recorded_count: 3,
        readback_verified_count: 2,
        recorded_ids: ["a", "b", "c"],
        verified_ids: ["a", "b"],
        incomplete_ids: ["d", "e"],
        stable_replay: false,
        entity_progress: []
      }
    });
    expect(s.status).toBe("partial_write");
    expect(phaseForTerminal(s, "a")).toBe("verified");
    expect(phaseForTerminal(s, "c")).toBe("recorded");
    expect(phaseForTerminal(s, "d")).toBe("proposed");
    const r = reducer(s, { type: "RETRY" });
    expect(r.status).toBe("recording");
  });
});
