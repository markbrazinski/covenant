/**
 * CausalGraph — deterministic layered lineage.
 *
 * LOCKED geometry (see `Covenant Causal Graph Lock.dc.html`): a shared governed
 * source, two intermediate columns, and a fixed terminal column. Layout is
 * computed ENTIRELY from path data (`TerminalPath.hops`) — NOT hard-coded by
 * entity name — so it is reusable for any affected set. No force-directed
 * physics, no pan/zoom for the canonical case, no lane cards behind paths, and
 * no connector crossings (each terminal owns a horizontal row track).
 *
 * Row tracks are shared with the ledger via `ROW_Y` so a graph terminal and its
 * ledger row align pixel-for-pixel; two-line terminal names do not break it.
 */
import { useMemo } from "react";
import type { CSSProperties, ReactNode } from "react";
import type { GovernedSourceReference, TerminalPath } from "../types/domain";
import { DISPOSITION, dispColor } from "./dispositions";

// ---- shared row-track definitions (graph terminals ↔ ledger rows) ----------
export const ROW_Y = [70, 210, 350, 490, 630];
const COL = { src: 12, c1: 224, c2: 436, term: 648 };
const W = { src: 150, c1: 150, c2: 150, term: 218 };
const SRC_RIGHT = COL.src + W.src; // 162
const CORRIDOR_X = 190; // orthogonal spine
const H = { src: 70, inter: 46, term: 64 };
const SRC_ROW = 2; // source sits on the middle track

export interface CausalGraphProps {
  source: GovernedSourceReference | null;
  terminals: TerminalPath[];
  /** how many hop tiers to draw (source-outward) — drives population reveal */
  revealTiers: number;
  /** how many terminal lanes to render */
  revealTerminals: number;
  /** whether disposition marks have resolved yet */
  showDispositions: boolean;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  /** show verified ✓ on terminals whose readback verified (recorded plan) */
  verified?: boolean;
  interactive: boolean;
  /** true → immediate complete layout, no transitions (reduced motion) */
  reducedMotion: boolean;
  /** presentation-only breadth-first reveal; state is gated by ImpactWorkspace */
  animateReveal: boolean;
}

interface Lane {
  t: TerminalPath;
  row: number;
  y: number;
  /** x of the last hop column reached at the current reveal, or null if none yet */
  drawnTo: number | null;
}

export function CausalGraph(props: CausalGraphProps) {
  const {
    terminals,
    revealTiers,
    revealTerminals,
    showDispositions,
    selectedId,
    onSelect,
    verified,
    interactive,
    reducedMotion,
    animateReveal
  } = props;

  const lanes = useMemo<Lane[]>(
    () =>
      terminals.map((t, row) => {
        // hop columns available for this path (0, 1 or 2 intermediates)
        const hopXs = [COL.c1, COL.c2].slice(0, t.hops.length);
        // tiers: edge 1 → hop1, edge 2 → hop2, final edge → terminal
        let drawnTo: number | null = null;
        // number of hop tiers revealed
        const hopsShown = Math.min(t.hops.length, Math.max(0, revealTiers));
        if (hopsShown > 0) drawnTo = hopXs[hopsShown - 1];
        // once all hop tiers are in AND this lane's terminal has arrived, reach it
        const terminalArrived = row < revealTerminals;
        if (terminalArrived) drawnTo = COL.term;
        else if (t.hops.length === 0 && revealTiers >= 1 && !terminalArrived) drawnTo = null;
        return { t, row, y: ROW_Y[row], drawnTo };
      }),
    [terminals, revealTiers, revealTerminals]
  );

  const dimmed = (id: string) => selectedId != null && id !== selectedId;
  const trans = reducedMotion ? "none" : "opacity .18s ease, stroke .18s ease";
  const entry = (delay: number) =>
    reducedMotion || !animateReveal
      ? undefined
      : `graphNodeReveal 360ms cubic-bezier(.2,.8,.2,1) ${delay}ms both`;

  // draw selected connector last so it sits above the shared corridor
  const orderedLanes = [...lanes].sort(
    (a, b) => (a.t.id === selectedId ? 1 : 0) - (b.t.id === selectedId ? 1 : 0)
  );

  return (
    <div style={{ position: "absolute", left: 0, top: 64, width: 900, height: 710 }}>
      <svg
        width={900}
        height={710}
        viewBox="0 0 900 710"
        style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
        aria-hidden="true"
      >
        {orderedLanes.map((lane) => {
          if (lane.drawnTo == null) return null;
          const sel = lane.t.id === selectedId;
          const d = `M${SRC_RIGHT},${ROW_Y[SRC_ROW]} H${CORRIDOR_X} V${lane.y} H${lane.drawnTo}`;
          return (
            <path
              key={lane.t.id}
              pathLength={1}
              className={animateReveal && !reducedMotion ? "graph-path-reveal" : undefined}
              d={d}
              fill="none"
              stroke={sel ? "var(--sel)" : "var(--neutral)"}
              strokeWidth={sel ? 2.5 : 1.5}
              style={{
                opacity: dimmed(lane.t.id) ? 0.28 : 1,
                transition: trans,
                animationDelay: "1120ms"
              }}
            />
          );
        })}
      </svg>

      {/* governed source */}
      <SourceNode
        key={terminals.length > 0 ? "resolved-source" : "pending-source"}
        source={props.source}
        animation={terminals.length > 0 ? entry(0) : undefined}
      />

      {lanes.map((lane) => {
        const { t, y, row } = lane;
        const sel = t.id === selectedId;
        const dim = dimmed(t.id);
        const nodes: ReactNode[] = [];
        const hopsShown = Math.min(t.hops.length, Math.max(0, revealTiers));
        t.hops.forEach((hop, i) => {
          if (i >= hopsShown) return;
          const x = i === 0 ? COL.c1 : COL.c2;
          nodes.push(
            <InterNode
              key={`${t.id}-h${i}`}
              x={x}
              y={y}
              label={hop.name}
              selected={sel}
              dim={dim}
              trans={trans}
              animation={entry(i === 0 ? 420 : 900)}
            />
          );
        });
        if (row < revealTerminals) {
          nodes.push(
            <TerminalNode
              key={`${t.id}-term`}
              t={t}
              y={y}
              selected={sel}
              dim={dim}
              showDisposition={showDispositions}
              verified={!!verified && t.disposition !== "human_review" && t.disposition !== "allowed"}
              interactive={interactive}
              onSelect={onSelect}
              trans={trans}
              animation={entry(1650)}
            />
          );
        }
        return <div key={t.id}>{nodes}</div>;
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------

function nodeBox(x: number, y: number, w: number, h: number): CSSProperties {
  return { position: "absolute", left: x, top: y - h / 2, width: w, height: h };
}

function SourceNode({
  source,
  animation
}: {
  source: GovernedSourceReference | null;
  animation?: string;
}) {
  return (
    <div
      style={{
        ...nodeBox(COL.src, ROW_Y[SRC_ROW], W.src, H.src),
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        padding: "10px 12px",
        border: "1.5px solid var(--line-2)",
        background: "var(--surface)",
        borderRadius: 2,
        animation
      }}
    >
      <span className="mono" style={{ fontSize: 12.5, fontWeight: 600, wordBreak: "break-all", lineHeight: 1.25 }}>
        {source?.displayName ?? "governed source"}
      </span>
      <span className="mono" style={{ fontSize: 10.5, color: source?.resolved ? "var(--verify)" : "var(--remediate)", marginTop: 5 }}>
        {source?.nativeType ?? "not exposed"} · {source?.resolved ? "✓ resolved" : "pending resolution"}
      </span>
    </div>
  );
}

function InterNode(p: {
  x: number;
  y: number;
  label: string;
  selected: boolean;
  dim: boolean;
  trans: string;
  animation?: string;
}) {
  return (
    <div
      style={{
        ...nodeBox(p.x, p.y, W.c1, H.inter),
        display: "flex",
        alignItems: "center",
        padding: "0 11px",
        borderRadius: 2,
        border: p.selected ? "2.5px solid var(--sel)" : "1.5px solid var(--line-2)",
        background: p.selected ? "var(--sel-wash)" : "var(--surface)",
        boxShadow: p.selected ? "inset 3px 0 0 var(--sel)" : "none",
        opacity: p.dim ? 0.4 : 1,
        transition: p.trans,
        animation: p.animation
      }}
    >
      <span
        className="mono"
        style={{ fontSize: 12, fontWeight: 500, color: p.dim ? "var(--muted)" : "var(--text-2)", wordBreak: "break-all", lineHeight: 1.2 }}
      >
        {p.label}
      </span>
    </div>
  );
}

function TerminalNode(p: {
  t: TerminalPath;
  y: number;
  selected: boolean;
  dim: boolean;
  showDisposition: boolean;
  verified: boolean;
  interactive: boolean;
  onSelect: (id: string | null) => void;
  trans: string;
  animation?: string;
}) {
  const meta = DISPOSITION[p.t.disposition];
  const color = dispColor(p.t.disposition);
  const style: CSSProperties = {
    ...nodeBox(COL.term, p.y, W.term, H.term),
    display: "flex",
    alignItems: "center",
    gap: 9,
    padding: "0 12px",
    borderRadius: 2,
    overflow: "hidden",
    textAlign: "left",
    border: p.selected ? "2.5px solid var(--sel)" : `1.5px solid ${p.showDisposition ? color : "var(--line-2)"}`,
    background: p.selected ? "var(--sel-wash)" : "var(--surface)",
    boxShadow: p.selected ? "inset 3px 0 0 var(--sel)" : "none",
    opacity: p.dim ? 0.42 : 1,
    cursor: p.interactive ? "pointer" : "default",
    transition: p.trans,
    animation: p.animation
  };
  const inner = (
    <>
      {p.showDisposition && (
        <span aria-hidden="true" style={{ color, fontSize: 14, width: 16, textAlign: "center", flex: "none" }}>
          {meta.mark}
        </span>
      )}
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: "block", fontSize: 13.5, fontWeight: 600, lineHeight: 1.2 }}>{p.t.displayName}</span>
        <span className="mono" style={{ display: "block", fontSize: 10, color: "var(--text-2)", marginTop: 2 }}>
          {p.t.assetType}
        </span>
      </span>
      {p.verified && (
        <span aria-hidden="true" className="mono" style={{ fontSize: 13, fontWeight: 700, color: "var(--verify)", flex: "none" }}>
          ✓
        </span>
      )}
      {p.showDisposition && (
        <span
          aria-hidden="true"
          style={{ flex: "none", width: 52, textAlign: "right", fontSize: 9, fontWeight: 700, letterSpacing: ".03em", textTransform: "uppercase", color, lineHeight: 1.2, marginLeft: 6 }}
        >
          {meta.label}
        </span>
      )}
    </>
  );
  if (!p.interactive) return <div style={style}>{inner}</div>;
  return (
    <button
      type="button"
      style={style}
      aria-pressed={p.selected}
      aria-label={`${p.t.displayName}, ${meta.label}${p.selected ? ", selected" : ""}`}
      onClick={() => p.onSelect(p.selected ? null : p.t.id)}
    >
      {inner}
    </button>
  );
}
