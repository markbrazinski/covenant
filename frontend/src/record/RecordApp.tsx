/**
 * RecordApp — route-driven orchestration for the Record visual system.
 *
 * Composes the ONE composition point (`PreviewDataSource`, swappable for a real
 * `GateApiDataSource`), the shared `useCovenant` hook (state machine + adapter),
 * and a History API router. It derives every workspace prop from the view + route and
 * owns two shell-level concerns the single-surface hook does not: primary-nav
 * routing and the persistent list of recorded Impact Plans.
 *
 * No policy lives here — the frontend renders backend decisions. All fixture
 * data and timers stay inside PreviewDataSource.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { PreviewDataSource, type PreviewFault } from "../adapter/PreviewDataSource";
import { GateApiDataSource } from "../adapter/GateApiDataSource";
import type { CovenantDataSource } from "../adapter/DataSource";
import { useCovenant } from "../state/useCovenant";
import {
  mapEvidence,
  mapRows,
  mapTally,
  mapTerminals,
  mapUnaffected
} from "../data/viewModels";
import type { ImpactPlanDTO, RecordedPlanDTO } from "../adapter/contracts";
import type {
  ChangeSummary,
  ImpactPlanRowVM,
  TallyCounts,
  UnaffectedControlVM,
  EvidenceBundleVM
} from "../types/domain";
import { AppShell, ContextStrip, type ShellStatus } from "./AppShell";
import { useHashRoute, usePrefersReducedMotion } from "./useHashRoute";
import { ChangesQueue, ReviewedChange } from "./Changes";
import { PlansIndex, GovernanceBackBand, type RecordedPlan } from "./Plans";
import { ImpactWorkspace, type LedgerMode } from "./ImpactWorkspace";
import {
  EvidenceBundle,
  GovernanceHold,
  RecordingBanner,
  VerifiedReceipt
} from "./ImpactLedger";
import "./theme.css";

const LEGACY_CHANGE_ALIAS = "atlas-v3-v4";

export function RecordApp() {
  const [route, navigate] = useHashRoute();
  const initialRoutedChangeId = useRef(
    route.changeId === LEGACY_CHANGE_ALIAS ? undefined : route.changeId
  ).current;
  const [forcedReduce, setForcedReduce] = useState(false);
  const reducedMotion = usePrefersReducedMotion(forcedReduce);
  const [fault, setFault] = useState<PreviewFault>("none");
  const [plans, setPlans] = useState<RecordedPlan[]>([]);
  const [recordedPlans, setRecordedPlans] = useState<RecordedPlanDTO[]>([]);
  const [plansLoaded, setPlansLoaded] = useState(false);
  const [planDTO, setPlanDTO] = useState<ImpactPlanDTO | null>(null);
  const [planSelectedId, setPlanSelectedId] = useState<string | null>(null);
  const [planEvidence, setPlanEvidence] = useState<EvidenceBundleVM | null>(null);

  // ONE composition point. Real HTTP is the default; fixture mode is explicit.
  const ds = useMemo<CovenantDataSource>(() => {
    if (import.meta.env.VITE_COVENANT_DATA_MODE === "fixture") {
      return new PreviewDataSource({ step: 340 });
    }
    return new GateApiDataSource({
      baseUrl:
        import.meta.env.VITE_COVENANT_API_URL ?? "http://127.0.0.1:8000",
      pollIntervalMs: 150,
      changeId: initialRoutedChangeId
    });
  }, [initialRoutedChangeId]);
  const preview = ds instanceof PreviewDataSource ? ds : null;
  useEffect(() => {
    if (preview) preview.setStep(reducedMotion ? 0 : 340);
  }, [ds, preview, reducedMotion]);
  useEffect(() => {
    preview?.setFault(fault);
  }, [preview, fault]);
  const initialImpactRoute = useRef(route.name === "impact").current;
  const view = useCovenant(ds, initialImpactRoute);

  // Preserve old demo/bookmark URLs, but replace them with the backend identity.
  useEffect(() => {
    if (
      route.changeId !== LEGACY_CHANGE_ALIAS ||
      !view.change?.changeId
    ) return;
    const suffix = route.name === "impact" ? "/impact" : "";
    navigate(
      `/changes/${encodeURIComponent(view.change.changeId)}${suffix}`,
      true
    );
  }, [navigate, route.changeId, route.name, view.change?.changeId]);
  useEffect(() => {
    if (route.name !== "impact") ds.cancelPending();
  }, [ds, route.name]);

  const refreshPlans = useCallback(async () => {
    const durable = await ds.getRecordedPlans();
    setRecordedPlans(durable);
    setPlans(durable.map((plan) => toRecordedPlan(plan, view.change)));
    setPlansLoaded(true);
    return durable;
  }, [ds, view.change]);

  useEffect(() => {
    void refreshPlans().catch(() => setPlansLoaded(true));
  }, [refreshPlans]);

  useEffect(() => {
    if (route.name !== "plan" || !route.planId) return;
    void ds.getImpactPlan(route.planId).then((plan) => {
      setPlanDTO(plan);
      setPlanSelectedId(null);
    });
  }, [ds, route.name, route.planId]);

  useEffect(() => {
    if (!planSelectedId || route.name !== "plan") {
      setPlanEvidence(null);
      return;
    }
    const terminal = planDTO?.terminals.find(
      (item) => item.decision_id === planSelectedId
    );
    void ds.getEvidence(planSelectedId).then((evidence) => {
      setPlanEvidence(
        mapEvidence(evidence, terminal?.display_name ?? planSelectedId)
      );
    });
  }, [ds, planDTO, planSelectedId, route.name]);

  // Navigate only after the adapter re-reads and reconciles every real receipt.
  const recordedOnce = useRef(false);
  useEffect(() => {
    if (view.status === "recorded_verified" && !recordedOnce.current) {
      recordedOnce.current = true;
      void ds.getReceipts().then(async (receipts) => {
        const activePlan = await ds.getImpactPlan();
        const expected = new Map(
          activePlan.terminals.map((terminal) => [
            terminal.response_identity,
            terminal.urn
          ])
        );
        const actual = new Map(
          receipts.map((receipt) => [
            receipt.response_identity,
            receipt.target_urn
          ])
        );
        if (
          expected.size === 0 ||
          receipts.length !== expected.size ||
          actual.size !== expected.size ||
          ![...expected].every(
            ([responseIdentity, urn]) =>
              actual.get(responseIdentity) === urn
          ) ||
          !receipts.every((receipt) => receipt.recorded && receipt.readback_verified)
        ) {
          recordedOnce.current = false;
          return;
        }
        const durable = await refreshPlans();
        const current = durable.find((plan) => plan.run_id === view.runId);
        if (!current) {
          recordedOnce.current = false;
          return;
        }
        setPlanDTO(current.plan);
        navigate(`#/impact-plans/${current.run_id}`);
      });
    }
    if (view.status === "awaiting_activation") recordedOnce.current = false;
  }, [ds, navigate, refreshPlans, view.runId, view.status]);

  // guard: plan detail requires a recorded plan
  useEffect(() => {
    if (
      plansLoaded &&
      route.name === "plan" &&
      !recordedPlans.some((plan) => plan.run_id === route.planId)
    ) {
      navigate("#/impact-plans");
    }
  }, [navigate, plansLoaded, recordedPlans, route.name, route.planId]);

  const activeChangeId = view.change?.changeId ?? route.changeId;
  const changePath = useCallback((suffix = "") => {
    if (!activeChangeId) return "/changes";
    return `/changes/${encodeURIComponent(activeChangeId)}${suffix}`;
  }, [activeChangeId]);

  const onActivate = useCallback(() => {
    view.activate();
    navigate(changePath("/impact"));
  }, [changePath, view, navigate]);

  // ---- dev controls (hidden unless ?dev) -----------------------------------
  const devEnabled =
    typeof location !== "undefined" && /[?&]dev\b/.test(location.search + location.hash);
  const injectDatahub = () => {
    if (!preview) return;
    preview.setFault("datahub_unavailable");
    setFault("datahub_unavailable");
    recordedOnce.current = false;
    view.reset();
    navigate(changePath("/impact"));
    setTimeout(() => view.activate(), 40);
  };
  const injectPartial = () => {
    if (!preview) return;
    preview.setFault("partial_write");
    setFault("partial_write");
  };
  const replay = () => {
    preview?.setFault("none");
    setFault("none");
    recordedOnce.current = false;
    view.reset();
    navigate(changePath());
  };

  const dev = devEnabled && preview ? (
    <div className="mono" style={{ flex: "none", display: "flex", alignItems: "center", gap: 8, padding: "8px 16px", background: "var(--ink)", color: "#fff", fontSize: 11, zIndex: 5 }}>
      <span style={{ color: "#b7b4ab", letterSpacing: ".08em" }}>DEV</span>
      <DevBtn onClick={replay}>Replay</DevBtn>
      <DevBtn onClick={() => setForcedReduce((v) => !v)}>{reducedMotion ? "Motion: reduced" : "Motion: full"}</DevBtn>
      <DevBtn onClick={injectDatahub}>Inject DataHub outage</DevBtn>
      <DevBtn onClick={injectPartial}>Inject partial write</DevBtn>
      <span style={{ flex: 1 }} />
      <span style={{ color: "#8b8e93" }}>status: {view.status} · fault {fault}</span>
    </div>
  ) : null;

  // ---- shell status --------------------------------------------------------
  const shellStatus: ShellStatus =
    route.name === "plan" ? "recorded" : shellStatusFrom(view.status);
  const crumb = crumbFor(route.name, view.change);

  // ---- route bodies --------------------------------------------------------
  let body: ReactNode = null;
  let strip: ReactNode = null;

  if (route.name === "changes") {
    body = (
      <ChangesQueue
        change={view.change}
        evidenceSummary={view.evidenceSummary}
        onReview={() => navigate(changePath())}
      />
    );
  } else if (route.name === "change") {
    body = (
      <ReviewedChange
        change={view.change}
        clauses={view.clauses}
        source={view.source}
        onActivate={onActivate}
      />
    );
  } else if (route.name === "impact") {
    ({ body, strip } = renderImpact());
  } else if (route.name === "plans") {
    body = <PlansIndex plans={plans} onOpen={(id) => navigate("#/impact-plans/" + id)} />;
  } else if (route.name === "plan") {
    ({ body, strip } = renderPlanDetail());
  }

  return (
    <div className="record-root">
      <AppShell route={route} status={shellStatus} navigate={navigate} crumb={crumb} strip={strip} dev={dev}>
        {body}
      </AppShell>
    </div>
  );

  // ------------------------------------------------------------------ impact
  function renderImpact(): { body: ReactNode; strip: ReactNode } {
    const st = view.status;
    const analyzing = view.analyzing || st === "activating";
    const unavailable = st === "datahub_unavailable";
    const recording = st === "recording" || st === "verifying_readbacks";
    const partial = st === "partial_write";
    const complete = st === "analysis_complete";
    const hasLedger = recording || partial || complete;

    const ledgerMode: LedgerMode = unavailable ? "unavailable" : analyzing ? "analyzing" : "ledger";
    const showDisp = hasLedger;

    const sel = view.selectedTerminalId;
    const selTerm = view.terminals.find((t) => t.id === sel);
    const graphLabel = unavailable
      ? "Lineage · DataHub unavailable"
      : analyzing
        ? "Lineage · awaiting completed DataHub analysis"
        : sel
          ? `Analysis complete · rendering five verified paths · ${selTerm?.displayName ?? ""} bound`
          : `Analysis complete · rendering ${view.terminalPathCount ?? view.terminals.length} verified paths · no terminal selected`;

    // evidence panel (complete only)
    let evidencePanel: ReactNode = null;
    if (complete) {
      if (!sel) {
        evidencePanel = (
          <div style={{ marginTop: 12, border: "1px solid var(--line)", background: "var(--surface-2)", padding: "14px 15px", textAlign: "center", fontSize: 12, color: "var(--muted)" }}>
            Select a terminal to bind its path, ledger row, and evidence.
          </div>
        );
      } else if (selTerm?.disposition === "human_review") {
        evidencePanel = (
          <GovernanceHold
            terminalName={selTerm.displayName}
            proposedAction={selTerm.proposedAction}
          />
        );
      } else if (view.evidence) {
        evidencePanel = <EvidenceBundle ev={view.evidence} />;
      }
    }

    const banner = recording ? (
      <RecordingBanner rec={view.machine.recProgress ?? null} partial={false} />
    ) : partial ? (
      <RecordingBanner rec={view.machine.recProgress ?? null} partial={true} />
    ) : null;

    const footer =
      complete ? (
        <div style={{ padding: "14px 22px", borderTop: "1px solid var(--line)" }}>
          <button type="button" onClick={view.record} style={{ width: "100%", fontSize: 14, fontWeight: 600, padding: 13, background: "var(--sel)", color: "#fff", border: "none", borderRadius: 2, cursor: "pointer" }}>
            Record 5 proposed responses in DataHub
          </button>
          <div className="mono" style={{ fontSize: 11, color: "var(--muted)", marginTop: 8, lineHeight: 1.5 }}>
            Records proposals only. Does not approve, execute, retrain, stop, or enforce.
          </div>
        </div>
      ) : partial ? (
        <div style={{ padding: "14px 22px", borderTop: "1px solid var(--line)" }}>
          <button type="button" onClick={view.retry} style={{ width: "100%", fontSize: 14, fontWeight: 600, padding: 13, background: "var(--remediate)", color: "#fff", border: "none", borderRadius: 2, cursor: "pointer" }}>
            Retry incomplete records
          </button>
        </div>
      ) : null;

    const stripNode = (
      <ContextStrip
        title={`${view.change?.provider ?? "Data-use"} — data-use change`}
        sub={`v${view.change?.fromVersion ?? "?"} → v${view.change?.toVersion ?? "?"} · effective ${view.change?.effectiveDate?.slice(0, 10) ?? "not exposed"}`}
        sourceText={unavailable ? "✕ resolution failed" : view.source?.resolved ? `✓ ${view.source.displayName} · ${view.source.nativeType}` : "resolving…"}
        sourceColor={unavailable ? "var(--stop)" : view.source?.resolved ? "var(--verify)" : "var(--remediate)"}
        derivedLabel="DERIVED"
        derivedText={unavailable ? "affected set cleared" : hasLedger ? (sel ? "selected · " + sel : `${view.terminalPathCount ?? view.terminals.length} exact paths · ${view.terminals.length} terminals`) : "intentionally empty"}
      />
    );

    return {
      strip: stripNode,
      body: (
        <ImpactWorkspace
          reducedMotion={reducedMotion}
          revealAnimationKey={view.runId ?? undefined}
          graphLabel={graphLabel}
          ledgerMode={ledgerMode}
          analyzingMsg={
            view.progressMessage ||
            "Resolving impact through DataHub. No terminals, counts, paths, dispositions, or tally are available yet."
          }
          terminals={view.terminals}
          source={view.source}
          revealTiers={view.graphRevealTiers}
          revealTerminals={view.graphRevealTerminals}
          showDispositions={showDisp}
          graphUnavailable={unavailable}
          interactive={complete}
          selectedId={sel}
          onSelect={view.select}
          rows={view.rows}
          tally={view.tally}
          showTally={hasLedger}
          unaffected={view.unaffected}
          controlNote="no change"
          banner={banner}
          evidencePanel={evidencePanel}
          footer={footer}
          onRetry={view.retry}
        />
      )
    };
  }

  // ------------------------------------------------------------- plan detail
  function renderPlanDetail(): { body: ReactNode; strip: ReactNode } {
    const terminals = planDTO ? mapTerminals(planDTO) : [];
    const tally: TallyCounts = mapTally(terminals);
    const rows: ImpactPlanRowVM[] = mapRows(terminals, "verified", planSelectedId);
    const unaffected: UnaffectedControlVM | null = planDTO?.unaffected_control
      ? mapUnaffected(planDTO.unaffected_control, true)
      : null;
    const recordedSource = view.source
      ? { ...view.source, resolved: true }
      : null;
    const sel = planSelectedId;
    const selectedTerm = terminals.find((terminal) => terminal.id === sel);

    let evidencePanel: ReactNode = null;
    if (selectedTerm?.disposition === "human_review") {
      evidencePanel = (
        <GovernanceHold
          terminalName={selectedTerm.displayName}
          proposedAction={selectedTerm.proposedAction}
        />
      );
    }
    else if (sel && planEvidence) evidencePanel = <EvidenceBundle ev={planEvidence} />;

    const strip = (
      <ContextStrip
        title={`${view.change?.provider ?? "Recorded"} — Impact Plan`}
        sub={`v${view.change?.fromVersion ?? "?"} → v${view.change?.toVersion ?? "?"} · recorded · replay-stable`}
        sourceText={`✓ ${view.source?.displayName ?? "governed source"} · ${view.source?.nativeType ?? "not exposed"}`}
        sourceColor="var(--verify)"
        derivedLabel="STATE"
        derivedText="recorded · replay-stable"
        rightChip={{ text: "Recorded · verified", kind: "verify" }}
      />
    );

    return {
      strip,
      body: (
        <ImpactWorkspace
          reducedMotion={reducedMotion}
          revealAnimationKey={route.planId}
          graphLabel={`Recorded plan · source → ${terminals.length} exact paths → terminals · readbacks verified`}
          ledgerMode="ledger"
          terminals={terminals}
          source={recordedSource}
          revealTiers={99}
          revealTerminals={terminals.length}
          showDispositions={true}
          graphUnavailable={false}
          verified={true}
          interactive={true}
          selectedId={sel}
          onSelect={setPlanSelectedId}
          rows={rows}
          tally={tally}
          showTally={true}
          unaffected={unaffected}
          controlNote="verified unmutated"
          banner={
            <VerifiedReceipt
              recordedCount={terminals.filter((terminal) => terminal.recorded).length}
              verifiedCount={terminals.filter((terminal) => terminal.readbackVerified).length}
            />
          }
          evidencePanel={evidencePanel}
          footer={
            <GovernanceBackBand
              terminalName={
                terminals.find((terminal) => terminal.disposition === "human_review")
                  ?.displayName ?? "Human-review terminal"
              }
              changeHref={changePath()}
              onBackToChange={() => navigate(changePath())}
            />
          }
          onRetry={view.retry}
        />
      )
    };
  }
}

function DevBtn({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" onClick={onClick} className="mono" style={{ fontSize: 11, fontWeight: 600, padding: "5px 10px", background: "#2a2e33", color: "#fff", border: "1px solid #3a3f45", borderRadius: 2, cursor: "pointer" }}>
      {children}
    </button>
  );
}

function shellStatusFrom(status: string): ShellStatus {
  switch (status) {
    case "activating":
    case "resolving_impact":
      return "resolving_impact";
    case "analysis_complete":
      return "complete";
    case "recording":
      return "recording";
    case "verifying_readbacks":
      return "verifying_readbacks";
    case "recorded_verified":
      return "recorded";
    case "datahub_unavailable":
      return "datahub_unavailable";
    case "partial_write":
      return "partial_write";
    default:
      return "idle";
  }
}

function crumbFor(name: string, change: ChangeSummary | null): string | undefined {
  const label = change
    ? `${change.provider} v${change.fromVersion}→v${change.toVersion}`
    : "Reviewed change";
  switch (name) {
    case "change":
      return `Changes / ${label}`;
    case "impact":
      return `Changes / ${label} / Impact`;
    case "plan":
      return `Impact Plans / ${label}`;
    default:
      return undefined;
  }
}

function toRecordedPlan(
  recorded: RecordedPlanDTO,
  change: ChangeSummary | null
): RecordedPlan {
  const tally = mapTally(mapTerminals(recorded.plan));
  return {
    id: recorded.run_id,
    title: `${change?.provider ?? "Recorded change"} — Impact Plan`,
    sub: `v${change?.fromVersion ?? "?"} → v${change?.toVersion ?? "?"} · recorded · replay-stable`,
    tally: `${tally.allowed} ● · ${tally.remediate} ▲ · ${tally.stopProposed} ◇ · ${tally.humanReview} ⟦⟧`,
    date: recorded.recorded_at?.slice(0, 10) ?? "not exposed",
    obligationId: change?.obligationId ?? "not exposed"
  };
}
