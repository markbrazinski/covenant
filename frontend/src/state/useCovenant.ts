import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import type { CovenantDataSource } from "../adapter/DataSource";
import type {
  ChangeSummary,
  Clause,
  GovernedSourceReference,
  TerminalPath,
  EvidenceBundleVM,
  UnaffectedControlVM,
  TallyCounts,
  ImpactPlanRowVM
} from "../types/domain";
import {
  reducer,
  initialState,
  hasAffectedSet,
  isAnalyzing,
  isRecordingLifecycle,
  globalPhase,
  phaseForTerminal,
  analysisTitle,
  type MachineState,
  type Status
} from "./machine";
import {
  mapChange,
  mapClauses,
  mapGovernedSource,
  mapTerminals,
  mapTally,
  mapRows,
  mapUnaffected,
  mapEvidence,
  evidenceSummaryLine
} from "../data/viewModels";
import type { UnaffectedControlDTO } from "../adapter/contracts";

export interface CovenantView {
  status: Status;
  machine: MachineState;
  // static / resolved content
  change: ChangeSummary | null;
  clauses: Clause[];
  evidenceSummary: string;
  source: GovernedSourceReference | null;
  // derived affected set
  terminals: TerminalPath[]; // full canonical list (stable lanes)
  graphRevealTerminals: number; // how many terminal lanes to draw
  graphRevealTiers: number; // how many hop tiers to draw for pending lanes
  tally: TallyCounts;
  rows: ImpactPlanRowVM[];
  unaffected: UnaffectedControlVM | null;
  evidence: EvidenceBundleVM | null;
  // flags
  selectedTerminalId: string | null;
  analyzing: boolean;
  recording: boolean;
  liveTitle: string;
  progressMessage: string;
  downstreamCount: number | null;
  terminalPathCount: number | null;
  runId: string | null;
  // actions
  activate: () => void;
  record: () => void;
  select: (id: string | null) => void;
  retry: () => void;
  reset: () => void;
}

const EMPTY_TALLY: TallyCounts = { allowed: 0, remediate: 0, stopProposed: 0, humanReview: 0 };

export function useCovenant(
  ds: CovenantDataSource,
  resumeImpactOnLoad = false
): CovenantView {
  const [machine, dispatch] = useReducer(reducer, initialState);
  const [change, setChange] = useState<ChangeSummary | null>(null);
  const [clauses, setClauses] = useState<Clause[]>([]);
  const [evidenceSummary, setEvidenceSummary] = useState("");
  const [sourceBase, setSourceBase] = useState<GovernedSourceReference | null>(null);
  const [terminals, setTerminals] = useState<TerminalPath[]>([]);
  const [controlDTO, setControlDTO] = useState<UnaffectedControlDTO | null>(null);
  const [evidence, setEvidence] = useState<EvidenceBundleVM | null>(null);
  const dsRef = useRef(ds);
  const planLoadedRef = useRef(false);
  dsRef.current = ds;

  // initial content load + adapter subscriptions
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [chg, ev, src] = await Promise.all([
          ds.getChange(),
          ds.getChangeEvidence(),
          ds.getGovernedSource()
        ]);
        if (!alive) return;
        setChange(mapChange(chg));
        setClauses(mapClauses(chg));
        setEvidenceSummary(evidenceSummaryLine(ev));
        setSourceBase(mapGovernedSource(src));
      } catch (error) {
        if (!alive) return;
        dispatch({
          type: "RUN_ERROR",
          e: {
            code: "DATAHUB_UNAVAILABLE",
            title: "Covenant API unavailable",
            detail: error instanceof Error ? error.message : "The API could not be reached.",
            clears_affected_set: true
          }
        });
      }
    })();

    const offRun = ds.observeRun((p) => {
      if (p.phase === "resolving_impact" || planLoadedRef.current) {
        dispatch({ type: "RUN_PROGRESS", p });
        return;
      }
      void ds.getImpactPlan().then((plan) => {
        if (!alive) return;
        planLoadedRef.current = true;
        setTerminals(mapTerminals(plan));
        setControlDTO(plan.unaffected_control);
        dispatch({ type: "RUN_PROGRESS", p });
      });
    });
    const offRec = ds.observeRecording((p) => dispatch({ type: "REC_PROGRESS", p }));
    const offErr = ds.observeErrors((e) => {
      if (e.clears_affected_set) {
        planLoadedRef.current = false;
        setTerminals([]);
        setControlDTO(null);
        dispatch({ type: "RUN_ERROR", e });
      } else {
        dispatch({ type: "REC_ERROR", e });
      }
    });
    if (resumeImpactOnLoad) void ds.resumeImpact();
    return () => {
      alive = false;
      planLoadedRef.current = false;
      ds.cancelPending();
      offRun();
      offRec();
      offErr();
    };
  }, [ds, resumeImpactOnLoad]);

  // load evidence for the selected terminal
  useEffect(() => {
    const id = machine.selectedTerminalId;
    if (!id || !hasAffectedSet(machine.status)) {
      setEvidence(null);
      return;
    }
    let alive = true;
    const term = terminals.find((t) => t.id === id);
    ds.getEvidence(id).then((dto) => {
      if (alive) setEvidence(mapEvidence(dto, term?.displayName ?? id));
    });
    return () => {
      alive = false;
    };
  }, [ds, machine.selectedTerminalId, machine.status, terminals]);

  // actions
  const activate = useCallback(() => {
    dispatch({ type: "ACTIVATE" });
    void dsRef.current.activate();
  }, []);
  const record = useCallback(() => {
    dispatch({ type: "RECORD" });
    void dsRef.current.recordProposedResponses(terminals.map((t) => t.id));
  }, [terminals]);
  const select = useCallback((id: string | null) => dispatch({ type: "SELECT", id }), []);
  const retry = useCallback(() => {
    const st = machine.status;
    dispatch({ type: "RETRY" });
    if (st === "datahub_unavailable") void dsRef.current.retry("resolve_lineage");
    else if (st === "partial_write") void dsRef.current.retry("record");
  }, [machine.status]);
  const reset = useCallback(() => {
    dispatch({ type: "RESET" });
    planLoadedRef.current = false;
    setTerminals([]);
    setControlDTO(null);
    void dsRef.current.reset();
  }, []);

  // derived source resolution
  const source: GovernedSourceReference | null = useMemo(() => {
    if (!sourceBase) return null;
    const resolved =
      sourceBase.resolved ||
      hasAffectedSet(machine.status);
    return { ...sourceBase, resolved };
  }, [sourceBase, machine.status]);

  // graph reveal
  const graphRevealTerminals = useMemo(() => {
    if (machine.status === "datahub_unavailable") return 0;
    if (hasAffectedSet(machine.status)) {
      return terminals.length;
    }
    return 0;
  }, [machine.status, machine.runProgress, terminals.length]);

  const graphRevealTiers = useMemo(() => {
    if (hasAffectedSet(machine.status)) return 99;
    if (machine.status === "resolving_impact" || machine.status === "activating") return 0;
    return 99;
  }, [machine.status, machine.runProgress]);

  const tally = useMemo(
    () => (hasAffectedSet(machine.status) ? mapTally(terminals) : EMPTY_TALLY),
    [terminals, machine.status]
  );

  const rows = useMemo<ImpactPlanRowVM[]>(() => {
    if (!hasAffectedSet(machine.status)) return [];
    const phase = isRecordingLifecycle(machine.status)
      ? (id: string) => phaseForTerminal(machine, id)
      : globalPhase(machine.status);
    return mapRows(
      terminals,
      phase,
      machine.selectedTerminalId,
      machine.recProgress?.entity_progress ?? []
    );
  }, [terminals, machine]);

  const unaffected = useMemo<UnaffectedControlVM | null>(() => {
    if (!controlDTO || !hasAffectedSet(machine.status)) return null;
    return mapUnaffected(controlDTO, machine.status === "recorded_verified");
  }, [controlDTO, machine.status]);

  return {
    status: machine.status,
    machine,
    change,
    clauses,
    evidenceSummary,
    source,
    terminals,
    graphRevealTerminals,
    graphRevealTiers,
    tally,
    rows,
    unaffected,
    evidence,
    selectedTerminalId: machine.selectedTerminalId,
    analyzing: isAnalyzing(machine.status),
    recording: isRecordingLifecycle(machine.status),
    liveTitle: analysisTitle(machine.status),
    progressMessage: machine.runProgress?.server_message ?? "",
    downstreamCount: machine.runProgress?.downstream_entity_count ?? null,
    terminalPathCount: machine.runProgress?.terminal_path_count ?? null,
    runId: machine.runProgress?.run_id ?? null,
    activate,
    record,
    select,
    retry,
    reset
  };
}
