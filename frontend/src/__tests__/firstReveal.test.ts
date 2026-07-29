import { describe, expect, it } from "vitest";
import { FirstRevealRegistry } from "../record/firstReveal";

describe("FirstRevealRegistry", () => {
  it("allows the Strict Mode owner to finish one reveal", () => {
    const registry = new FirstRevealRegistry();
    expect(registry.claim("RUN-1", "strict-owner")).toBe(true);
    expect(registry.claim("RUN-1", "strict-owner")).toBe(true);
    registry.complete("RUN-1", "strict-owner");
    expect(registry.claim("RUN-1", "strict-owner")).toBe(false);
  });

  it("blocks navigation and rerender owners after the first claim", () => {
    const registry = new FirstRevealRegistry();
    expect(registry.claim("RUN-1", "impact-workspace")).toBe(true);
    expect(registry.claim("RUN-1", "recorded-plan-workspace")).toBe(false);
  });

  it("allows one fresh reveal after a page reload", () => {
    const firstPage = new FirstRevealRegistry();
    firstPage.claim("RUN-1", "owner");
    firstPage.complete("RUN-1", "owner");

    const reloadedPage = new FirstRevealRegistry();
    expect(reloadedPage.claim("RUN-1", "new-owner")).toBe(true);
  });
});
