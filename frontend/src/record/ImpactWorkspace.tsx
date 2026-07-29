/**
 * ImpactWorkspace — the two-pane analysis surface: data-driven causal graph on
 * the left, Impact Plan ledger on the right. A pure presenter — RecordApp
 * derives every prop from the shared `useCovenant` view + route, so this file
 * holds no policy and never computes the affected set.
 */
import type {
  TerminalPath,
  ImpactPlanRowVM,
  TallyCounts,
  UnaffectedControlVM,
  GovernedSourceReference
} from "../types/domain";
import { useId, useLayoutEffect, useState } from "react";
import type { ReactNode } from "react";
import { CausalGraph } from "./CausalGraph";
import { ImpactTally, ImpactPlanRow, UnaffectedRow } from "./ImpactLedger";
import { pageFirstRevealRegistry } from "./firstReveal";

export type LedgerMode = "analyzing" | "unavailable" | "ledger";

export interface WorkspaceProps {
  reducedMotion: boolean;
  /** Stable backend run identity. Its completed graph reveal runs once per tab. */
  revealAnimationKey?: string;
  graphLabel: string;
  ledgerMode: LedgerMode;
  analyzingMsg?: string;
  // graph
  source: GovernedSourceReference | null;
  terminals: TerminalPath[];
  revealTiers: number;
  revealTerminals: number;
  showDispositions: boolean;
  graphUnavailable: boolean;
  verified?: boolean;
  interactive: boolean;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  // ledger
  rows: ImpactPlanRowVM[];
  tally: TallyCounts;
  showTally: boolean;
  unaffected: UnaffectedControlVM | null;
  controlNote: string;
  banner?: ReactNode;
  evidencePanel?: ReactNode;
  footer?: ReactNode;
  onRetry: () => void;
}

const COL_HEADERS = [
  { left: 12, w: 150, text: "SOURCE" },
  { left: 224, w: 150, text: "INTERMEDIATE 1" },
  { left: 436, w: 150, text: "INTERMEDIATE 2" },
  { left: 648, w: 218, text: "TERMINAL" }
];

// Longest presentation beat: terminal nodes begin at 1650ms and run for
// 360ms. Remove reveal classes once that one-shot window is over so later
// lifecycle rerenders (recording/readback) cannot restart the graph animation.
const FIRST_REVEAL_WINDOW_MS = 2100;

export function ImpactWorkspace(p: WorkspaceProps) {
  const animateReveal = useFirstReveal(
    p.revealAnimationKey,
    p.ledgerMode === "ledger" && p.terminals.length > 0,
    p.reducedMotion
  );
  const showColHeaders = !p.graphUnavailable && (p.revealTiers > 0 || p.revealTerminals > 0 || p.ledgerMode === "ledger");
  return (
    <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
      {/* GRAPH PANE */}
      <div style={{ width: 900, flex: "none", borderRight: "1px solid var(--line)", background: "var(--surface-2)", position: "relative" }}>
        <div className="mono" style={{ position: "absolute", left: 26, top: 14, fontSize: 11, fontWeight: 700, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--muted)" }}>
          {p.graphLabel}
        </div>
        {showColHeaders &&
          COL_HEADERS.map((h) => (
            <div key={h.text} className="mono" style={{ position: "absolute", top: 40, left: h.left, width: h.w, textAlign: "center", fontSize: 9, letterSpacing: ".06em", color: "#b3b1a9" }}>
              {h.text}
            </div>
          ))}

        {p.graphUnavailable ? (
          <div style={{ position: "absolute", inset: "70px 26px 26px", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", gap: 12, textAlign: "center" }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--stop)" }}>✕ DataHub unavailable</div>
            <div className="mono" style={{ fontSize: 12, color: "#7a4038", maxWidth: 420, lineHeight: 1.6 }}>
              The affected set has been cleared. No cached plan is shown as current. No terminals, dispositions, or tally are derived.
            </div>
          </div>
        ) : (
          <CausalGraph
            source={p.source}
            terminals={p.terminals}
            revealTiers={p.revealTiers}
            revealTerminals={p.revealTerminals}
            showDispositions={p.showDispositions}
            selectedId={p.selectedId}
            onSelect={p.onSelect}
            verified={p.verified}
            interactive={p.interactive}
            reducedMotion={p.reducedMotion}
            animateReveal={animateReveal}
          />
        )}
      </div>

      {/* LEDGER PANE */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", background: "var(--surface)", overflow: "hidden" }}>
        {p.ledgerMode === "analyzing" && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", padding: "0 30px" }}>
            <div className="mono" style={{ border: "1px dashed var(--line-2)", background: "repeating-linear-gradient(45deg,#faf9f6,#faf9f6 7px,#f2f1ec 7px,#f2f1ec 14px)", padding: 22, textAlign: "center", fontSize: 12, color: "var(--muted)" }}>
              <span className="rec-pulse" aria-hidden="true">◐ </span>{p.analyzingMsg}
            </div>
            <div style={{ fontSize: 13, color: "var(--text-2)", marginTop: 16, lineHeight: 1.6, textAlign: "center" }}>
              No downstream uses derived yet. No affected assets, counts, paths, dispositions, or tally appear until DataHub derives the set.
            </div>
          </div>
        )}

        {p.ledgerMode === "unavailable" && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", padding: "0 30px", gap: 14 }}>
            <div style={{ border: "1.5px solid var(--stop)", background: "#fbf3f1", padding: "16px 18px" }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--stop)" }}>✕ DataHub unavailable — affected set cleared</div>
              <div className="mono" style={{ fontSize: 11.5, color: "#7a4038", marginTop: 6, lineHeight: 1.6 }}>
                No cached plan is shown as current. Nothing was proposed. Re-run impact analysis when DataHub is reachable.
              </div>
            </div>
            <button type="button" onClick={p.onRetry} style={{ alignSelf: "flex-start", fontSize: 13, fontWeight: 600, padding: "11px 16px", background: "var(--ink)", color: "#fff", border: "none", borderRadius: 2, cursor: "pointer" }}>
              Retry impact analysis
            </button>
          </div>
        )}

        {p.ledgerMode === "ledger" && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
            {p.banner}
            <div className={animateReveal ? "impact-outcomes-reveal" : undefined} style={{ padding: "10px 22px", display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "2px solid var(--ink)" }}>
              <span style={{ fontSize: 16, fontWeight: 600 }}>Impact Plan</span>
              {p.showTally && <ImpactTally tally={p.tally} />}
            </div>
            <div className={animateReveal ? "impact-outcomes-reveal" : undefined} style={{ flex: 1, overflow: "auto", padding: "12px 22px" }}>
              <div style={{ display: "grid", gap: 6 }}>
                {p.rows.map((r) => (
                  <ImpactPlanRow key={r.id} row={r} onSelect={(id) => p.onSelect(id)} />
                ))}
                {p.unaffected && <UnaffectedRow control={p.unaffected} />}
              </div>
              {p.evidencePanel}
            </div>
            {p.footer}
          </div>
        )}
      </div>
    </div>
  );
}

function useFirstReveal(
  runId: string | undefined,
  ready: boolean,
  reducedMotion: boolean
): boolean {
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const ownerId = useId();

  useLayoutEffect(() => {
    if (!runId || !ready || reducedMotion) {
      setActiveKey(null);
      return;
    }
    if (!pageFirstRevealRegistry.claim(runId, ownerId)) {
      setActiveKey(null);
      return;
    }
    setActiveKey(runId);
    const timeout = window.setTimeout(() => {
      pageFirstRevealRegistry.complete(runId, ownerId);
      setActiveKey((current) => (current === runId ? null : current));
    }, FIRST_REVEAL_WINDOW_MS);
    return () => window.clearTimeout(timeout);
  }, [ownerId, ready, reducedMotion, runId]);

  return Boolean(runId && activeKey === runId && ready && !reducedMotion);
}
