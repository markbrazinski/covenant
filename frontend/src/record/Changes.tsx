/**
 * Changes routes — the reviewed data-use change queue and the reviewed change
 * with explicit human activation. No affected set, dispositions, or counts are
 * derived until a person activates.
 */
import type {
  ChangeSummary,
  Clause,
  GovernedSourceReference
} from "../types/domain";

// ---- /changes : queue ------------------------------------------------------
export function ChangesQueue({
  change,
  evidenceSummary,
  onReview
}: {
  change: ChangeSummary | null;
  evidenceSummary: string;
  onReview: () => void;
}) {
  const effective = change?.effectiveDate?.slice(0, 10) ?? "not exposed";
  return (
    <div style={{ flex: 1, padding: "44px 54px", overflow: "auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", paddingBottom: 16, borderBottom: "2px solid var(--ink)" }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0, letterSpacing: "-.01em" }}>Data-use Changes</h1>
        <span className="mono" style={{ fontSize: 12, color: "var(--text-2)" }}>
          Reviewed changes requiring impact planning · {change ? "1 open" : "loading"}
        </span>
      </div>
      {change && <button
        type="button"
        onClick={onReview}
        style={{ width: "100%", textAlign: "left", display: "flex", gap: 24, alignItems: "center", padding: "26px 20px", border: "none", borderBottom: "1px solid var(--line)", boxShadow: "inset 3px 0 0 var(--ink)", background: "var(--surface)", cursor: "pointer" }}
      >
        <div style={{ flex: 2.4 }}>
          <div style={{ fontSize: 20, fontWeight: 600 }}>{change.provider} — data-use change</div>
          <div className="mono" style={{ fontSize: 12, color: "var(--text-2)", marginTop: 7 }}>
            {change.obligationId} · agreement version v{change.fromVersion} → v{change.toVersion} · {evidenceSummary}
          </div>
        </div>
        <div style={{ flex: 1 }}>
          <div className="mono" style={{ fontSize: 10, color: "var(--muted)" }}>EFFECTIVE</div>
          <div className="mono" style={{ fontSize: 15, marginTop: 3 }}>{effective}</div>
        </div>
        <div style={{ flex: 1.2 }}>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".05em", textTransform: "uppercase", color: "var(--remediate)" }}>Impact analysis required</span>
        </div>
        <span style={{ width: 150, flex: "none", textAlign: "center", fontSize: 14, fontWeight: 600, padding: 13, background: "var(--ink)", color: "#fff", borderRadius: 2 }}>Review change</span>
      </button>}
      <p style={{ fontSize: 13, lineHeight: 1.6, color: "var(--muted)", marginTop: 24, maxWidth: 780 }}>
        One reviewed data-use change is open. Sparse but intentional — no downstream uses have been derived yet, so none are shown. Analysis is explicitly human-initiated.
      </p>
    </div>
  );
}

// ---- /changes/:changeId : reviewed change + activation ---------------------
export function ReviewedChange(props: {
  change: ChangeSummary | null;
  clauses: Clause[];
  source: GovernedSourceReference | null;
  onActivate: () => void;
}) {
  const { change, clauses, source, onActivate } = props;
  const effectColor: Record<string, string> = {
    allowed: "var(--allowed)",
    prohibited: "var(--stop)",
    review: "var(--human)"
  };
  return (
    <div style={{ flex: 1, padding: "36px 54px", overflow: "auto", display: "flex", gap: 34, alignItems: "flex-start" }}>
      <div style={{ flex: 1.5, minWidth: 0 }}>
        <div className="mono" style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--muted)" }}>Reviewed data-use change</div>
        <h1 style={{ fontSize: 26, fontWeight: 800, margin: "10px 0 0", letterSpacing: "-.01em" }}>
          {change ? `${change.provider} v${change.fromVersion} → v${change.toVersion}` : "Atlas Signals v3 → v4"}
        </h1>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 }}>
          {[change?.obligationId ?? "not exposed", `effective ${change?.effectiveDate?.slice(0, 10) ?? "not exposed"}`, change?.reviewState ?? "loading"].map((t) => (
            <span key={t} className="mono" style={{ fontSize: 11.5, color: "var(--text-2)", border: "1px solid var(--line)", background: "var(--surface)", padding: "5px 10px" }}>{t}</span>
          ))}
        </div>
        <div style={{ marginTop: 22, border: "1px solid var(--line)", background: "var(--surface)", borderRadius: 2 }}>
          <div className="mono" style={{ padding: "12px 16px", borderBottom: "1px solid var(--line)", fontSize: 11, fontWeight: 700, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--muted)" }}>
            Material change · {clauses.length} rule deltas
          </div>
          <div style={{ padding: "14px 16px", display: "grid", gap: 10 }}>
            {clauses.map((c, i) => (
              <div key={i} style={{ display: "flex", gap: 12, alignItems: "baseline" }}>
                <span className="mono" style={{ fontSize: 11, fontWeight: 600, color: effectColor[c.effect] ?? "var(--text-2)", width: 78, flex: "none", textTransform: "uppercase" }}>{c.effect}</span>
                <span style={{ fontSize: 13, color: "#3a3f45" }}>{c.text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div style={{ width: 420, flex: "none", border: "1.5px solid var(--ink)", background: "var(--surface)", borderRadius: 2, padding: 22 }}>
        <div className="mono" style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--muted)" }}>Governed source</div>
        <div style={{ marginTop: 10, padding: "12px 14px", border: "1.5px solid var(--line-2)", borderRadius: 2 }}>
          <div className="mono" style={{ fontSize: 13, fontWeight: 600 }}>{source?.displayName ?? "loading source"}</div>
          <div className="mono" style={{ fontSize: 11, color: "var(--text-2)", marginTop: 4 }}>
            {source?.nativeType ?? "not exposed"} · candidate source · <span style={{ color: "var(--remediate)" }}>pending DataHub resolution</span>
          </div>
        </div>
        <p style={{ fontSize: 12.5, lineHeight: 1.6, color: "var(--text-2)", margin: "18px 0 0" }}>
          Authorizes impact analysis only. Does not enact, approve, or execute the obligation change.
          {" "}No affected uses, dispositions, paths, or counts are derived until a person activates.
        </p>
        <button
          type="button"
          onClick={onActivate}
          style={{ width: "100%", marginTop: 18, fontSize: 14, fontWeight: 600, padding: 14, background: "var(--ink)", color: "#fff", border: "none", borderRadius: 2, cursor: "pointer" }}
        >
          Activate for impact analysis
        </button>
        <div className="mono" style={{ fontSize: 10, color: "var(--muted)", marginTop: 10, textAlign: "center", letterSpacing: ".04em" }}>
          SYNTHETIC TEST APPROVAL · reviewer: synthetic_test
        </div>
      </div>
    </div>
  );
}
