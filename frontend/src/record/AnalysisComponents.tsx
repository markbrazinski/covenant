import {
  useRef,
  useState,
  type DragEvent,
  type ReactNode,
} from "react";

export type AnalysisStatusKind = "neutral" | "amber" | "green" | "warn";
export type ProgressVisualState =
  | "pending"
  | "active"
  | "complete"
  | "failed";

const STATUS_GLYPH: Record<AnalysisStatusKind, string> = {
  neutral: "○",
  amber: "◐",
  green: "●",
  warn: "✕",
};

export function AnalysisShell({
  status,
  children,
}: {
  status: { kind: AnalysisStatusKind; label: string; announcement: string };
  children: ReactNode;
}) {
  return (
    <div className="analysis-canvas">
      <section className="analysis-shell" aria-label="Covenant analysis">
        <div className="vh" aria-live="polite">
          {status.announcement}
        </div>
        <header className="analysis-header">
          <div className="serif analysis-wordmark">Covenant</div>
          <div className="mono analysis-breadcrumb">Analyses / New</div>
          <AnalysisStatusPill kind={status.kind} label={status.label} />
        </header>
        {children}
      </section>
    </div>
  );
}

export function AnalysisStatusPill({
  kind,
  label,
}: {
  kind: AnalysisStatusKind;
  label: string;
}) {
  return (
    <span className={`analysis-status analysis-status--${kind}`}>
      <span aria-hidden="true">{STATUS_GLYPH[kind]}</span>
      {label}
    </span>
  );
}

export function AnalysisWorkspaceLayout({
  main,
  activity,
}: {
  main: ReactNode;
  activity: ReactNode;
}) {
  return (
    <div className="analysis-workspace">
      <main className="analysis-main">{main}</main>
      <aside className="analysis-activity-column" aria-label="Agent activity">
        {activity}
      </aside>
    </div>
  );
}

export function AnalysisButton({
  kind = "teal",
  children,
  ...props
}: {
  kind?: "teal" | "ink" | "link";
  children: ReactNode;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      className={`analysis-button analysis-button--${kind} ${props.className ?? ""}`}
    >
      {children}
    </button>
  );
}

export function AnalysisCard({
  tint = "default",
  className = "",
  children,
}: {
  tint?: "default" | "matched" | "green" | "warn" | "amber";
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`analysis-card analysis-card--${tint} ${className}`}>
      {children}
    </section>
  );
}

export function PhaseList({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <section className="analysis-phase-list" aria-label={label}>
      <h3 className="mono analysis-section-label">{label}</h3>
      <div className="analysis-phase-stack">{children}</div>
    </section>
  );
}

export function PhaseRow({
  label,
  state,
  failedTag,
}: {
  label: string;
  state: ProgressVisualState;
  failedTag?: string;
}) {
  const tag =
    state === "active"
      ? "In progress"
      : state === "complete"
        ? "Done"
        : state === "failed"
          ? failedTag ?? "Failed"
          : null;
  return (
    <div className={`analysis-phase analysis-phase--${state}`}>
      <span className="analysis-phase-dot" aria-hidden="true">
        {state === "complete" ? "✓" : state === "failed" ? "✕" : ""}
      </span>
      <span className="analysis-phase-label">{label}</span>
      {tag && <span className="analysis-phase-tag">{tag}</span>}
      <span className="vh">{state}</span>
    </div>
  );
}

export function ReceiptCard({
  label,
  state,
  call,
  result,
}: {
  label: string;
  state: Exclude<ProgressVisualState, "pending">;
  call: string;
  result: string;
}) {
  return (
    <article className={`analysis-receipt analysis-receipt--${state}`}>
      <div className="analysis-receipt-header">
        <span className="analysis-receipt-dot" aria-hidden="true">
          {state === "complete" ? "✓" : state === "failed" ? "✕" : ""}
        </span>
        <strong>{label}</strong>
        <span className="analysis-receipt-tag">
          {state === "active"
            ? "Running"
            : state === "complete"
              ? "Done"
              : "Failed"}
        </span>
      </div>
      <div className="mono analysis-receipt-call">{call}</div>
      <div className="mono analysis-receipt-result">{result}</div>
    </article>
  );
}

export function AgentActivityPanel({
  children,
}: {
  children?: ReactNode;
}) {
  return (
    <section className="analysis-agent-panel">
      <h2 className="mono analysis-section-label">Agent activity</h2>
      <div className="analysis-receipt-stack">
        {children ?? (
          <p className="analysis-empty-activity">
            No activity yet. Upload an agreement to begin.
          </p>
        )}
      </div>
    </section>
  );
}

export interface SelectedDocument {
  name: string;
  sizeLabel: string;
  sha256Label: string;
}

export function DocumentSlot({
  document,
  disabled = false,
  onSelect,
}: {
  document: SelectedDocument | null;
  disabled?: boolean;
  onSelect: (file: File) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const accept = (files: FileList | null) => {
    const file = files?.item(0);
    if (file) onSelect(file);
  };
  const drop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    if (!disabled) accept(event.dataTransfer.files);
  };
  return (
    <div
      className={`analysis-document-slot ${
        document ? "analysis-document-slot--filled" : ""
      } ${dragging ? "analysis-document-slot--dragging" : ""}`}
      onDragEnter={(event) => {
        event.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={() => setDragging(false)}
      onDrop={drop}
    >
      <input
        ref={inputRef}
        className="vh"
        type="file"
        accept=".pdf,.md,.txt,application/pdf,text/markdown,text/plain"
        disabled={disabled}
        onChange={(event) => accept(event.currentTarget.files)}
        aria-label="Select candidate agreement"
      />
      {document ? (
        <>
          <div className="analysis-document-topline">
            <span className="mono analysis-section-label">
              Candidate version · uploaded
            </span>
            <AnalysisButton
              kind="link"
              disabled={disabled}
              onClick={() => inputRef.current?.click()}
            >
              Replace
            </AnalysisButton>
          </div>
          <div className="analysis-document-file">
            <span className="mono analysis-pdf-chip" aria-hidden="true">
              PDF
            </span>
            <span>
              <strong className="mono analysis-document-name">
                {document.name}
              </strong>
              <span className="mono analysis-document-meta">
                {document.sizeLabel} · sha256: {document.sha256Label}
              </span>
            </span>
          </div>
        </>
      ) : (
        <div className="analysis-document-empty">
          <span className="mono analysis-section-label">Candidate version</span>
          <AnalysisButton
            disabled={disabled}
            onClick={() => inputRef.current?.click()}
          >
            Select document
          </AnalysisButton>
          <span className="analysis-helper">or drop a PDF here</span>
        </div>
      )}
    </div>
  );
}

export function MatchedAgreementCard({
  vendor,
  obligationId,
  currentVersion,
  effectiveDate,
  subdued = false,
}: {
  vendor: string;
  obligationId: string;
  currentVersion: string;
  effectiveDate: string;
  subdued?: boolean;
}) {
  return (
    <AnalysisCard
      tint="matched"
      className={`analysis-matched-card ${subdued ? "analysis-matched-card--subdued" : ""}`}
    >
      <span className="analysis-match-check" aria-hidden="true">
        ✓
      </span>
      <div className="mono analysis-section-label">
        Matched to governed agreement
      </div>
      <h2 className="serif analysis-vendor">{vendor}</h2>
      <div className="analysis-field-grid">
        <AnalysisField label="Obligation" value={obligationId} />
        <AnalysisField
          label="In-effect prior version"
          value={`${currentVersion} · effective ${effectiveDate}`}
        />
      </div>
    </AnalysisCard>
  );
}

export function AnalysisNotice({
  kind,
  title,
  body,
  children,
}: {
  kind: "verified" | "rejected" | "no-match" | "error";
  title: string;
  body: string;
  children?: ReactNode;
}) {
  const tint =
    kind === "verified" ? "green" : kind === "no-match" ? "amber" : "warn";
  return (
    <AnalysisCard tint={tint} className={`analysis-notice analysis-notice--${kind}`}>
      <h2 className="serif">{title}</h2>
      <p>{body}</p>
      {children}
    </AnalysisCard>
  );
}

export function AnalysisField({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <span className="analysis-field">
      <span className="mono analysis-field-label">{label}</span>
      <span className="mono analysis-field-value">{value}</span>
    </span>
  );
}
