/**
 * AppShell — top nav, breadcrumb, context strip, live status.
 *
 * No sidebar (locked). Two primary destinations only: Changes / Impact Plans.
 * The status chip and a visually-hidden live region announce analysis and
 * recording for screen readers.
 */
import type { Route } from "./useHashRoute";
import type { ReactNode } from "react";

export type ShellStatus =
  | "idle"
  | "resolving_impact"
  | "complete"
  | "recording"
  | "verifying_readbacks"
  | "recorded"
  | "datahub_unavailable"
  | "partial_write";

const STATUS: Record<ShellStatus, { text: string; color: string; dot: string; pulse: boolean; announce: string }> = {
  idle: { text: "Ready for impact analysis", color: "var(--text-2)", dot: "○", pulse: false, announce: "" },
  resolving_impact: { text: "Resolving impact through DataHub", color: "var(--remediate)", dot: "◐", pulse: true, announce: "Resolving impact through DataHub." },
  complete: { text: "Impact Plan ready", color: "var(--verify)", dot: "●", pulse: false, announce: "Impact analysis complete. Returned paths are ready for inspection." },
  recording: { text: "Recording proposals", color: "var(--remediate)", dot: "◐", pulse: true, announce: "Recording proposed responses to DataHub." },
  verifying_readbacks: { text: "Verifying readbacks", color: "var(--remediate)", dot: "◐", pulse: true, announce: "Verifying DataHub readbacks." },
  recorded: { text: "Recorded · Verified", color: "var(--verify)", dot: "●", pulse: false, announce: "Recorded. Readbacks verified." },
  datahub_unavailable: { text: "DataHub unavailable", color: "var(--stop)", dot: "✕", pulse: false, announce: "DataHub unavailable. Affected set cleared." },
  partial_write: { text: "Partial write — action needed", color: "var(--remediate)", dot: "◐", pulse: false, announce: "Partial write. Some records incomplete." }
};

export function AppShell(props: {
  route: Route;
  status: ShellStatus;
  navigate: (h: string, replace?: boolean) => void;
  crumb?: string;
  strip?: ReactNode;
  children: ReactNode;
  dev?: ReactNode;
}) {
  const { route, status, navigate, crumb, strip, children, dev } = props;
  const s = STATUS[status];
  const changesActive = route.name === "changes" || route.name === "change" || route.name === "impact";
  const plansActive = route.name === "plans" || route.name === "plan";

  return (
    <div style={{ minHeight: "100vh", background: "var(--app-bg)", display: "flex", justifyContent: "center", alignItems: "flex-start", padding: "24px 24px 60px" }}>
      <div
        role="application"
        aria-label="Covenant"
        style={{ width: 1440, height: 900, background: "var(--frame-bg)", border: "1px solid var(--line-2)", borderRadius: 2, overflow: "hidden", display: "flex", flexDirection: "column", position: "relative" }}
      >
        <div className="vh" aria-live="polite">{s.announce}</div>

        <header style={{ height: 60, flex: "none", display: "flex", alignItems: "center", gap: 30, padding: "0 34px", borderBottom: "2px solid var(--ink)", background: "var(--surface)", zIndex: 3 }}>
          <div className="serif" style={{ fontSize: 20, fontWeight: 600 }}>Covenant</div>
          <nav aria-label="Primary" style={{ display: "flex", gap: 10 }}>
            <NavItem label="Changes" active={changesActive} onClick={() => navigate("#/changes")} />
            <NavItem label="Impact Plans" active={plansActive} onClick={() => navigate("#/impact-plans")} />
          </nav>
          <div style={{ flex: 1 }} />
          <span className="mono" aria-label={s.text} style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12, color: s.color }}>
            <span className={s.pulse ? "rec-pulse" : undefined} aria-hidden="true">{s.dot}</span>
            {s.text}
          </span>
        </header>

        {crumb && (
          <div className="mono" style={{ height: 32, flex: "none", display: "flex", alignItems: "center", padding: "0 34px", background: "var(--surface-2)", borderBottom: "1px solid var(--line)", fontSize: 11.5, color: "var(--text-2)" }}>
            {crumb}
          </div>
        )}

        {strip}

        <main style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>{children}</main>

        {dev}
      </div>
    </div>
  );
}

function NavItem({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      style={{
        fontSize: 14,
        fontWeight: active ? 700 : 600,
        padding: "6px 2px",
        border: "none",
        background: "none",
        cursor: "pointer",
        color: active ? "var(--ink)" : "var(--muted)",
        borderBottom: active ? "2px solid var(--sel)" : "2px solid transparent"
      }}
    >
      {label}
    </button>
  );
}

/** Context strip under the breadcrumb on the impact / plan routes. */
export function ContextStrip(props: {
  title: string;
  sub: string;
  sourceText: string;
  sourceColor?: string;
  derivedLabel: string;
  derivedText: string;
  rightChip?: { text: string; kind: "verify" };
}) {
  return (
    <div style={{ height: 60, flex: "none", display: "flex", alignItems: "center", padding: "0 34px", background: "var(--surface)", borderBottom: "1px solid var(--line)" }}>
      <div style={{ paddingRight: 24 }}>
        <div style={{ fontWeight: 600, fontSize: 16 }}>{props.title}</div>
        <div className="mono" style={{ fontSize: 11, color: "var(--text-2)" }}>{props.sub}</div>
      </div>
      <StripCol label="GOVERNED SOURCE" text={props.sourceText} color={props.sourceColor} />
      <StripCol label={props.derivedLabel} text={props.derivedText} />
      <div style={{ flex: 1 }} />
      {props.rightChip && (
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".05em", textTransform: "uppercase", color: "var(--verify)", border: "1px solid var(--verify-line)", background: "var(--verify-wash)", padding: "5px 11px", borderRadius: 2 }}>
          {props.rightChip.text}
        </span>
      )}
    </div>
  );
}

function StripCol({ label, text, color }: { label: string; text: string; color?: string }) {
  return (
    <div style={{ borderLeft: "1px solid var(--line)", padding: "0 24px" }}>
      <div className="mono" style={{ fontSize: 10, color: "var(--muted)" }}>{label}</div>
      <div className="mono" style={{ fontSize: 11.5, color: color ?? "var(--ink)", marginTop: 2 }}>{text}</div>
    </div>
  );
}
