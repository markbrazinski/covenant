import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  AgentActivityPanel,
  AnalysisNotice,
  AnalysisStatusPill,
  DocumentSlot,
  MatchedAgreementCard,
  PhaseRow,
  ReceiptCard,
  type ProgressVisualState,
} from "../record/AnalysisComponents";

const markup = (
  component: Parameters<typeof renderToStaticMarkup>[0],
) => renderToStaticMarkup(component);

describe("Beat 0 analysis components", () => {
  it("renders every status-pill variant with text and glyph", () => {
    for (const kind of ["neutral", "amber", "green", "warn"] as const) {
      const html = markup(
        createElement(AnalysisStatusPill, { kind, label: `${kind} state` }),
      );
      expect(html).toContain(`analysis-status--${kind}`);
      expect(html).toContain(`${kind} state`);
    }
  });

  it("renders every phase state with a non-color text alternative", () => {
    for (const state of [
      "pending",
      "active",
      "complete",
      "failed",
    ] as ProgressVisualState[]) {
      const html = markup(
        createElement(PhaseRow, {
          label: "Verifying candidate",
          state,
        }),
      );
      expect(html).toContain(`analysis-phase--${state}`);
      expect(html).toContain(`>${state}<`);
    }
  });

  it("renders active, complete, and failed receipt evidence", () => {
    for (const state of ["active", "complete", "failed"] as const) {
      const html = markup(
        createElement(ReceiptCard, {
          label: "Registry lookup",
          state,
          call: "lookup_governed_agreement(Atlas Signals, ATLAS-LIC-004)",
          result: state === "active" ? "awaiting response…" : "→ MATCH",
        }),
      );
      expect(html).toContain(`analysis-receipt--${state}`);
      expect(html).toContain("Registry lookup");
      expect(html).toContain("lookup_governed_agreement");
    }
  });

  it("renders honest empty and filled document-slot states", () => {
    const empty = markup(
      createElement(DocumentSlot, {
        document: null,
        onSelect: () => undefined,
      }),
    );
    expect(empty).toContain("Select document");
    expect(empty).toContain("or drop a PDF here");

    const filled = markup(
      createElement(DocumentSlot, {
        document: {
          name: "atlas_license_v4.pdf",
          sizeLabel: "418 KB",
          sha256Label: "3b7e10…",
        },
        onSelect: () => undefined,
      }),
    );
    expect(filled).toContain("Candidate version · uploaded");
    expect(filled).toContain("atlas_license_v4.pdf");
    expect(filled).toContain("sha256: 3b7e10…");
  });

  it("renders the live registry date instead of the obsolete design date", () => {
    const html = markup(
      createElement(MatchedAgreementCard, {
        vendor: "Atlas Signals",
        obligationId: "ATLAS-LIC-004",
        currentVersion: "v3",
        effectiveDate: "2025-07-01",
      }),
    );
    expect(html).toContain("effective 2025-07-01");
    expect(html).not.toContain("2024-08-01");
  });

  it("renders empty activity and all terminal notice families", () => {
    expect(markup(createElement(AgentActivityPanel))).toContain(
      "No activity yet. Upload an agreement to begin.",
    );
    for (const kind of [
      "verified",
      "rejected",
      "no-match",
      "error",
    ] as const) {
      const html = markup(
        createElement(AnalysisNotice, {
          kind,
          title: `${kind} title`,
          body: `${kind} detail`,
        }),
      );
      expect(html).toContain(`analysis-notice--${kind}`);
      expect(html).toContain(`${kind} detail`);
    }
  });
});
