import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { PreviewDataSource } from "../adapter/PreviewDataSource";
import type { RunProgressDTO, RecordingProgressDTO, ErrorProjectionDTO } from "../adapter/contracts";

describe("PreviewDataSource", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("emits a deterministic run culminating in complete", async () => {
    const ds = new PreviewDataSource({ step: 10 });
    const phases: RunProgressDTO["phase"][] = [];
    ds.observeRun((p) => phases.push(p.phase));
    await ds.activate();
    vi.advanceTimersByTime(10 * 20);
    expect(phases[0]).toBe("resolving_impact");
    expect(phases[phases.length - 1]).toBe("complete");
  });

  it("clears the affected set on DataHub unavailability", async () => {
    const ds = new PreviewDataSource({ step: 10, fault: "datahub_unavailable" });
    const errors: ErrorProjectionDTO[] = [];
    ds.observeErrors((e) => errors.push(e));
    await ds.activate();
    vi.advanceTimersByTime(100);
    expect(errors[0].code).toBe("DATAHUB_UNAVAILABLE");
    expect(errors[0].clears_affected_set).toBe(true);
  });

  it("records five and verifies five with stable replay", async () => {
    const ds = new PreviewDataSource({ step: 5 });
    const events: RecordingProgressDTO[] = [];
    ds.observeRecording((p) => events.push(p));
    const ids = ["internal_executive_dashboard", "churn_model_a", "propensity_model_b", "customer_delivery_job", "anonymized_segment_derivative"];
    await ds.recordProposedResponses(ids);
    vi.advanceTimersByTime(5 * 30);
    const last = events[events.length - 1];
    expect(last.phase).toBe("reconciled");
    expect(last.recorded_count).toBe(5);
    expect(last.readback_verified_count).toBe(5);
    expect(last.stable_replay).toBe(true);
  });

  it("partial write leaves work incomplete then retry completes with no duplicate identities", async () => {
    const ds = new PreviewDataSource({ step: 5, fault: "partial_write" });
    const events: RecordingProgressDTO[] = [];
    ds.observeRecording((p) => events.push(p));
    const ids = ["internal_executive_dashboard", "churn_model_a", "propensity_model_b", "customer_delivery_job", "anonymized_segment_derivative"];
    await ds.recordProposedResponses(ids);
    vi.advanceTimersByTime(5 * 30);
    const partial = events.find((e) => e.phase === "partial")!;
    expect(partial.recorded_count).toBe(3);
    expect(partial.readback_verified_count).toBe(2);
    expect(partial.incomplete_ids.length).toBeGreaterThan(0);

    // retry resumes only the incomplete ids
    const after: RecordingProgressDTO[] = [];
    ds.observeRecording((p) => after.push(p));
    await ds.retry("record");
    vi.advanceTimersByTime(5 * 30);
    const last = after[after.length - 1];
    expect(last.phase).toBe("reconciled");
    expect(last.readback_verified_count).toBe(5);
    // no id verified twice
    expect(new Set(last.verified_ids).size).toBe(last.verified_ids.length);
  });
});
