/**
 * Disposition presentation — shape + label + colour, in ONE place.
 *
 * Product-honesty is in the shapes: there is no "approved" / "executed" /
 * "stopped" mark. `stop_proposed` reads "Stop proposed" (never "stopped");
 * `human_review` reads "Governance review" and is never given a proposed action.
 */
import type { DecisionDisposition, Disposition } from "../types/domain";

export interface DispositionMeta {
  mark: string; // shape glyph
  label: string; // text label (never colour-only)
  colorVar: string; // CSS custom property name
}

export const DISPOSITION: Record<Disposition, DispositionMeta> = {
  allowed: { mark: "\u25CF", label: "Allowed", colorVar: "--allowed" }, // ●
  remediate: { mark: "\u25B2", label: "Remediate", colorVar: "--remediate" }, // ▲
  stop_proposed: { mark: "\u25C7", label: "Stop proposed", colorVar: "--stop" }, // ◇
  human_review: { mark: "\u27E6\u27E7", label: "Governance review", colorVar: "--human" }, // ⟦⟧
  unaffected: { mark: "\u25CB", label: "Unaffected", colorVar: "--neutral" } // ○
};

export function dispColor(d: Disposition): string {
  return `var(${DISPOSITION[d].colorVar})`;
}

/** Standing decision-requirement copy per disposition (constant across phases). */
export const DECISION_REQUIREMENT: Record<DecisionDisposition, string> = {
  allowed: "No response required",
  remediate: "Owner remediation decision required",
  stop_proposed: "Owner stop decision required · not stopped",
  human_review: "Governance review required · unresolved"
};

/** The canonical exact receipt line — nothing implies execution/approval. */
export const RECEIPT_HEADLINE =
  "5 proposed responses recorded in DataHub · 5 readbacks verified.";
export const RECEIPT_SUBLINE =
  "Recorded \u2260 executed · nothing approved, stopped, retrained, or enforced";
export const RECEIPT_VERIFICATION =
  "Verified by matching response IDs and target URNs across MCP tag and SDK receipt readbacks";
