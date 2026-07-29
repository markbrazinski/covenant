/**
 * Impact Plans routes — index (empty until a plan is recorded; newest first)
 * and the persistent recorded-plan detail.
 */
export interface RecordedPlan {
  id: string;
  title: string;
  sub: string;
  tally: string;
  date: string;
  obligationId: string;
}

// ---- /impact-plans : index -------------------------------------------------
export function PlansIndex({ plans, onOpen }: { plans: RecordedPlan[]; onOpen: (id: string) => void }) {
  return (
    <div style={{ flex: 1, padding: "44px 54px", overflow: "auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", paddingBottom: 16, borderBottom: "2px solid var(--ink)" }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0, letterSpacing: "-.01em" }}>Impact Plans</h1>
        <span className="mono" style={{ fontSize: 12, color: "var(--text-2)" }}>Recorded plans · {plans.length}</span>
      </div>

      {plans.length === 0 ? (
        <div style={{ marginTop: 40, border: "1px dashed var(--line-2)", background: "var(--surface)", borderRadius: 2, padding: 48, textAlign: "center" }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text-2)" }}>No Impact Plans recorded yet</div>
          <div className="mono" style={{ fontSize: 12, color: "var(--muted)", marginTop: 8 }}>Record an Impact Plan from a reviewed change to see it here.</div>
        </div>
      ) : (
        <div style={{ display: "grid", gap: 10, marginTop: 18 }}>
          {plans.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => onOpen(p.id)}
              style={{ width: "100%", textAlign: "left", display: "flex", gap: 24, alignItems: "center", padding: "22px 20px", border: "1px solid var(--line)", boxShadow: "inset 3px 0 0 var(--verify)", background: "var(--surface)", cursor: "pointer", borderRadius: 2 }}
            >
              <div style={{ flex: 2.4 }}>
                <div style={{ fontSize: 18, fontWeight: 600 }}>{p.title}</div>
                <div className="mono" style={{ fontSize: 12, color: "var(--text-2)", marginTop: 6 }}>{p.obligationId} · {p.sub}</div>
              </div>
              <div style={{ flex: 1 }}>
                <div className="mono" style={{ fontSize: 10, color: "var(--muted)" }}>TALLY</div>
                <div className="mono" style={{ fontSize: 13, marginTop: 3 }}>{p.tally}</div>
              </div>
              <div style={{ flex: 1 }}>
                <div className="mono" style={{ fontSize: 10, color: "var(--muted)" }}>RECORDED</div>
                <div className="mono" style={{ fontSize: 13, marginTop: 3 }}>{p.date}</div>
              </div>
              <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".05em", textTransform: "uppercase", color: "var(--verify)", border: "1px solid var(--verify-line)", background: "var(--verify-wash)", padding: "6px 12px", borderRadius: 2 }}>
                Recorded · verified
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Footer band on the recorded-plan detail: governance still unresolved + link back. */
export function GovernanceBackBand({
  terminalName,
  changeHref,
  onBackToChange
}: {
  terminalName: string;
  changeHref: string;
  onBackToChange: () => void;
}) {
  return (
    <div style={{ padding: "12px 22px", borderTop: "1px solid var(--human)", background: "var(--human-wash)" }}>
      <div style={{ fontWeight: 700, fontSize: 13, color: "#4a3277" }}>⟦⟧ Governance review required · unresolved</div>
      <div className="mono" style={{ fontSize: 11, color: "#6a5292", marginTop: 4 }}>
        {terminalName} · held for human judgment ·{" "}
        <a
          href={changeHref}
          onClick={(e) => {
            e.preventDefault();
            onBackToChange();
          }}
        >
          originating change ↗
        </a>
      </div>
    </div>
  );
}
