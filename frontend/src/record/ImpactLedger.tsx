/**
 * Impact Plan ledger — tally, rows, evidence, recording progress, receipt.
 *
 * Rows share the terminal row order and the ONE `selectedTerminalId` circuit:
 * clicking a row === clicking its graph terminal. Nothing here implies a
 * response was approved, executed, retrained, stopped, or enforced; verified
 * green appears only after a readback verifies.
 */
import type {
  ImpactPlanRowVM,
  TallyCounts,
  EvidenceBundleVM,
  UnaffectedControlVM
} from "../types/domain";
import type { RecordingProgressDTO } from "../adapter/contracts";
import {
  DISPOSITION,
  dispColor,
  RECEIPT_SUBLINE,
  RECEIPT_VERIFICATION
} from "./dispositions";

// ---- tally -----------------------------------------------------------------
export function ImpactTally({ tally }: { tally: TallyCounts }) {
  const parts = [
    { n: tally.allowed, d: "allowed" as const },
    { n: tally.remediate, d: "remediate" as const },
    { n: tally.stopProposed, d: "stop_proposed" as const },
    { n: tally.humanReview, d: "human_review" as const }
  ];
  return (
    <span className="mono" style={{ fontSize: 14, fontWeight: 700, display: "inline-flex", gap: 12 }}>
      {parts.map((p) => (
        <span key={p.d} style={{ color: dispColor(p.d) }} aria-label={`${p.n} ${DISPOSITION[p.d].label}`}>
          <span aria-hidden="true">{p.n} {DISPOSITION[p.d].mark}</span>
        </span>
      ))}
    </span>
  );
}

// ---- one ledger row --------------------------------------------------------
export function ImpactPlanRow({
  row,
  onSelect
}: {
  row: ImpactPlanRowVM;
  onSelect: (id: string) => void;
}) {
  const meta = DISPOSITION[row.disposition];
  const color = dispColor(row.disposition);
  return (
    <button
      type="button"
      onClick={() => onSelect(row.id)}
      aria-pressed={row.selected}
      aria-label={`${row.displayName}, ${meta.label}${row.selected ? ", selected" : ""}`}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 13,
        padding: "9px 13px",
        borderRadius: 2,
        width: "100%",
        textAlign: "left",
        cursor: "pointer",
        background: row.selected ? "var(--sel-wash)" : "var(--surface)",
        border: row.selected ? "2px solid var(--sel)" : "1px solid var(--line)",
        boxShadow: row.selected ? "inset 3px 0 0 var(--sel)" : "none"
      }}
    >
      <span aria-hidden="true" style={{ color, fontSize: 14, width: 16, textAlign: "center", flex: "none" }}>
        {meta.mark}
      </span>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: "block", fontSize: 14, fontWeight: 600 }}>{row.displayName}</span>
        <span className="mono" style={{ display: "block", fontSize: 11, color: "var(--text-2)", marginTop: 2 }}>
          {row.lifecycleMarker}
        </span>
        <span className="mono" style={{ display: "block", fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
          {row.decisionRequirement}
        </span>
        {row.verified && (
          <span className="mono" style={{ display: "block", fontSize: 9.5, color: "var(--muted)", marginTop: 3, wordBreak: "break-all" }}>
            response {row.responseIdentity} · target {row.urn ?? "not exposed"}
            {row.datahubUrl && (
              <>
                {" · "}
                <a
                  href={row.datahubUrl}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={`Open ${row.displayName} properties in DataHub`}
                  onClick={(event) => event.stopPropagation()}
                >
                  Open in DataHub ↗
                </a>
              </>
            )}
          </span>
        )}
      </span>
      {row.verified && (
        <span aria-hidden="true" className="mono" style={{ fontSize: 12, fontWeight: 700, color: "var(--verify)" }}>
          ✓
        </span>
      )}
      <span
        style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".05em", textTransform: "uppercase", color, whiteSpace: "nowrap", flex: "none" }}
      >
        {meta.label}
      </span>
    </button>
  );
}

// ---- unaffected control (never counted in the tally) -----------------------
export function UnaffectedRow({ control }: { control: UnaffectedControlVM }) {
  return (
    <div
      style={{ display: "flex", alignItems: "center", gap: 13, padding: "8px 13px", border: "1px dashed var(--line-2)", borderRadius: 2, opacity: 0.85 }}
    >
      <span aria-hidden="true" style={{ color: "var(--muted)", width: 16, textAlign: "center" }}>
        {DISPOSITION.unaffected.mark}
      </span>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 600 }}>{control.displayName}</div>
        <div className="mono" style={{ fontSize: 11, color: "var(--text-2)", marginTop: 2 }}>
          {control.assetType} · {control.note}
        </div>
      </div>
      <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".05em", textTransform: "uppercase", color: "var(--muted)" }}>
        Unaffected
      </span>
    </div>
  );
}

// ---- evidence bundle -------------------------------------------------------
export function EvidenceBundle({ ev }: { ev: EvidenceBundleVM }) {
  if (!ev.available) {
    return (
      <div style={{ marginTop: 12, border: "1px solid var(--stop)", background: "#fbf3f1", padding: "12px 15px" }}>
        <div style={{ fontWeight: 700, fontSize: 13, color: "var(--stop)" }}>Evidence unavailable</div>
        <div className="mono" style={{ fontSize: 11, color: "#7a4038", marginTop: 5 }}>
          The runtime did not return evidence for this terminal. Nothing is fabricated in its place.
        </div>
      </div>
    );
  }
  return (
    <div style={{ marginTop: 12, border: "1px solid var(--ink)", background: "var(--surface-2)", padding: "12px 15px" }}>
      <div className="mono" style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--muted)" }}>
        Evidence · {ev.terminalName}
      </div>
      <div style={{ display: "grid", gap: 5, marginTop: 8 }}>
        {ev.primary.concat(ev.secondary).map((f, i) => (
          <div key={i} style={{ display: "flex", gap: 10, fontSize: 11.5 }}>
            <span className="mono" style={{ width: 76, flex: "none", color: "var(--muted)" }}>{f.k}</span>
            <span className={f.mono ? "mono" : undefined} style={{ fontStyle: f.italic ? "italic" : "normal", color: f.italic ? "var(--stop)" : "var(--ink)", wordBreak: "break-all" }}>
              {f.v}
            </span>
          </div>
        ))}
      </div>
      {ev.datahubUrl && (
        <a
          className="mono"
          href={ev.datahubUrl}
          target="_blank"
          rel="noreferrer"
          aria-label={`Open ${ev.terminalName} properties in DataHub`}
          style={{ display: "inline-block", marginTop: 9, fontSize: 11 }}
        >
          Open native Properties in DataHub ↗
        </a>
      )}
    </div>
  );
}

/** Governance-review terminal: no proposed action, held for a person. */
export function GovernanceHold({
  terminalName,
  proposedAction
}: {
  terminalName: string;
  proposedAction: string;
}) {
  return (
    <div style={{ marginTop: 12, border: "1px solid var(--human)", background: "var(--human-wash)", padding: "12px 15px" }}>
      <div style={{ fontWeight: 700, fontSize: 13, color: "#4a3277" }}>
        {DISPOSITION.human_review.mark} Governance review required · unresolved
      </div>
      <div className="mono" style={{ fontSize: 11, color: "#6a5292", marginTop: 5, lineHeight: 1.5 }}>
        {terminalName} · {proposedAction} · Held for human judgment.
      </div>
    </div>
  );
}

// ---- recording progress banner --------------------------------------------
export function RecordingBanner({ rec, partial }: { rec: RecordingProgressDTO | null; partial: boolean }) {
  if (partial) {
    return (
      <div style={{ margin: "16px 22px 0", border: "1.5px solid var(--remediate)", background: "#fbf7ee", padding: "12px 15px" }}>
        <div style={{ fontWeight: 700, fontSize: 12 }}>◐ Partial write — records incomplete</div>
        <div className="mono" style={{ fontSize: 11, marginTop: 5, lineHeight: 1.5, opacity: 0.85 }}>
          Verified rows are marked; incomplete rows are NOT shown verified. Retry targets only incomplete records.
        </div>
      </div>
    );
  }
  const v = rec?.readback_verified_count ?? 0;
  const target = rec?.target_count ?? 0;
  return (
    <div style={{ margin: "16px 22px 0", border: "1.5px solid var(--remediate)", background: "#fbf7ee", padding: "12px 15px" }}>
      <div className="rec-pulse" style={{ fontWeight: 700, fontSize: 12 }}>◐ Recording to DataHub · {v}/{target} readbacks verified</div>
      <div className="mono" style={{ fontSize: 11, marginTop: 5, lineHeight: 1.5, opacity: 0.85 }}>
        Writing proposed responses and evidence, then reading each back to verify.
      </div>
    </div>
  );
}

// ---- verified receipt (Source Serif headline is allowed here) --------------
export function VerifiedReceipt({
  recordedCount,
  verifiedCount
}: {
  recordedCount: number;
  verifiedCount: number;
}) {
  return (
    <div style={{ margin: "16px 22px 0", border: "1px solid var(--verify-line)", background: "var(--verify-wash)", padding: "13px 15px" }}>
      <div className="serif" style={{ fontWeight: 700, fontSize: 16, lineHeight: 1.3, color: "#0f5030" }}>
        {recordedCount} proposed responses recorded in DataHub · {verifiedCount} readbacks verified.
      </div>
      <div className="mono" style={{ fontSize: 11, color: "#2f6b4c", marginTop: 5 }}>
        {RECEIPT_SUBLINE}
      </div>
      <div className="mono" style={{ fontSize: 10.5, color: "#2f6b4c", marginTop: 5 }}>
        How verified · {RECEIPT_VERIFICATION}. Open any verified row’s native Properties page to inspect the recorded values.
      </div>
    </div>
  );
}
