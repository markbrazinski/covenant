import { describe, it, expect } from "vitest";
import {
  dispositionFromDTO,
  lifecycleMarker,
  mapTerminals,
  mapTally,
  mapRows,
  mapUnaffected,
  mapEvidence,
  DECISION_REQUIREMENT,
  writebackMarker
} from "../data/viewModels";
import * as C from "../data/canonical";

describe("viewModels", () => {
  it("maps disposition enum casing", () => {
    expect(dispositionFromDTO("STOP_PROPOSED")).toBe("stop_proposed");
    expect(dispositionFromDTO("HUMAN_REVIEW")).toBe("human_review");
  });

  it("keeps the canonical 1/2/1/1 tally", () => {
    const terms = mapTerminals(C.impactPlan);
    const t = mapTally(terms);
    expect(t).toEqual({ allowed: 1, remediate: 2, stopProposed: 1, humanReview: 1 });
    expect(terms).toHaveLength(5);
  });

  it("never fabricates URNs (omitted when not exposed)", () => {
    const terms = mapTerminals(C.impactPlan);
    expect(terms.every((t) => t.urn === undefined)).toBe(true);
  });

  it("enforces honest lifecycle language", () => {
    expect(lifecycleMarker("allowed", "proposed")).toBe("Proposed · not recorded");
    expect(lifecycleMarker("stop_proposed", "verified")).toContain("not stopped");
    expect(lifecycleMarker("human_review", "verified")).toContain("Unresolved");
    // human review never proposes an automatic action
    expect(DECISION_REQUIREMENT.human_review).toContain("no automatic action proposed");
    // no phase ever produces an "approved"/"executed"/"enforced" string
    for (const d of ["allowed", "remediate", "stop_proposed", "human_review"] as const) {
      for (const p of ["proposed", "recorded", "verified"] as const) {
        const m = lifecycleMarker(d, p).toLowerCase();
        expect(m).not.toMatch(/approved|executed|enforced|retrained|unlearned/);
      }
    }
  });

  it("marks exactly one human-review row and no bulk approval", () => {
    const terms = mapTerminals(C.impactPlan);
    const rows = mapRows(terms, "proposed", null);
    expect(rows.filter((r) => r.human)).toHaveLength(1);
  });

  it("maps every real writeback event to the locked row copy", () => {
    const base = {
      entity_id: "churn_model_a",
      terminal_display_name: "Churn Model A",
      sequence_index: 1,
      phase_started_at: "2026-07-29T20:00:00Z",
      response_id: "COV-real",
      failure: null
    };
    const expected = {
      PENDING: "Proposed · not recorded",
      WRITING: "Writing to DataHub…",
      WRITTEN: "Written · verifying readback",
      VERIFYING_MCP: "Verifying MCP tag readback",
      MCP_VERIFIED: "MCP verified · verifying SDK readback",
      VERIFYING_SDK: "Verifying SDK property readback",
      SDK_VERIFIED: "Both readbacks verified",
      VERIFIED: "Recorded · readback verified ✓"
    } as const;
    for (const [phase, marker] of Object.entries(expected)) {
      expect(
        writebackMarker("remediate", {
          ...base,
          phase: phase as keyof typeof expected,
          response_id: phase === "PENDING" || phase === "WRITING"
            ? null
            : base.response_id
        })
      ).toBe(marker);
    }
    expect(
      writebackMarker("remediate", {
        ...base,
        phase: "FAILED",
        failure: {
          category: "PARTIAL_WRITE",
          safe_message: "Native write failed safely"
        }
      })
    ).toBe("Failed · Native write failed safely");
  });

  it("upgrades unaffected-control proof only after reconciliation", () => {
    const control = C.impactPlan.unaffected_control!;
    expect(mapUnaffected(control, false)).toMatchObject({
      note: "Outside affected set",
      verified: false
    });
    expect(mapUnaffected(control, true)).toMatchObject({
      note: "Outside affected set · verified unmutated",
      verified: true
    });
  });

  it("evidence is decision-first with expandable secondary detail", () => {
    const vm = mapEvidence(C.churnEvidence, "Churn Model A");
    expect(vm.available).toBe(true);
    expect(vm.primary[0].k).toBe("Triggering clause");
    expect(vm.primary[1].k).toBe("DataHub lineage path");
    expect(vm.primary[2].k).toBe("Proposed response");
    // URN shown as "not exposed", never fabricated
    const urn = vm.secondary.find((f) => f.k === "URN");
    expect(urn?.v).toBe("not exposed");
  });

  it("surfaces an honest unavailable evidence bundle", () => {
    const vm = mapEvidence({ ...C.churnEvidence, available: false }, "Churn Model A");
    expect(vm.available).toBe(false);
    expect(vm.primary).toHaveLength(0);
  });
});
