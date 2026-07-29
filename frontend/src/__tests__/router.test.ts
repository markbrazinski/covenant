import { describe, expect, it } from "vitest";
import { parseHash } from "../record/useHashRoute";

describe("change routes", () => {
  it("parses any backend change identity", () => {
    expect(parseHash("/changes/CHANGE-483b8ee4b44cfe3f7eda")).toEqual({
      name: "change",
      changeId: "CHANGE-483b8ee4b44cfe3f7eda"
    });
    expect(parseHash("/changes/atlas-v3-v4/impact")).toEqual({
      name: "impact",
      changeId: "atlas-v3-v4"
    });
  });

  it("keeps collection and plan routes distinct", () => {
    expect(parseHash("/changes")).toEqual({ name: "changes" });
    expect(parseHash("/impact-plans/RUN-real")).toEqual({
      name: "plan",
      planId: "RUN-real"
    });
  });
});
