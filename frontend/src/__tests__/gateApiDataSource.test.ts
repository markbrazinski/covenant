import { afterEach, describe, expect, it, vi } from "vitest";
import {
  GateApiDataSource,
  dataHubPropertiesUrl,
  isReconciled
} from "../adapter/GateApiDataSource";
import type {
  ErrorProjectionDTO,
  RecordingProgressDTO,
  RunProgressDTO
} from "../adapter/contracts";

const summary = {
  change_id: "CHANGE-real",
  obligation_id: "ATLAS-LIC-004",
  provider_name: "Atlas Signals",
  superseded_version: 3,
  candidate_version: 4,
  effective_at: "2026-08-01T00:00:00Z",
  source_asset: {
    urn: "urn:li:dataset:(urn:li:dataPlatform:covenant,northstar.vendor_demographics_raw,DEV)",
    display_name: "vendor_demographics_raw",
    native_type: "Dataset"
  },
  lifecycle_state: "AWAITING_REVIEW",
  evidence_state: "SUPPORTED",
  material_rule_count: 4,
  unresolved_gap_count: 0,
  candidate_hash: "a".repeat(64)
};

const decision = {
  path_id: "P2",
  decision_id: "COV-real-churn",
  asset_urn: "urn:li:mlModel:(urn:li:dataPlatform:covenant,northstar.churn_model_a,DEV)",
  display_name: "Churn Model A",
  native_type: "mlModel",
  owner: "urn:li:corpGroup:northstar_model_ops",
  usage_class: "ml_training",
  disposition: "REMEDIATE",
  decision_state: "AWAITING_HUMAN_APPROVAL",
  proposed_action: "owner decision: clean rebuild, retrain, or deprecate",
  paths: [[summary.source_asset.urn, "urn:features", "urn:train", "urn:model"]],
  path_nodes: [[
    { urn: summary.source_asset.urn, display_name: "vendor_demographics_raw", native_type: "dataset" },
    { urn: "urn:features", display_name: "training_features_a", native_type: "dataset" },
    { urn: "urn:train", display_name: "train_churn_model_a", native_type: "dataProcessInstance" },
    { urn: "urn:model", display_name: "Churn Model A", native_type: "mlModel" }
  ]],
  triggering_rule: { citation: { quote: "- machine-learning training is prohibited;" } },
  controlling_policy_rule: "v4.ml_training.prohibited_rebuild_or_deprecate",
  confidence_meaning: "deterministic metadata rule matched",
  actor_class: "agent_system_recommendation",
  metadata_interfaces: {
    lineage: "DataHub MCP get_lineage_paths_between",
    ownership: "DataHub MCP get_entities",
    usage_and_terminal: "DataHub SDK native property-aspect read"
  },
  mcp_path_verified: true,
  readback_verified: false,
  datahub_url: "http://localhost:9002/mlModels/urn:model/"
};

const activation = run({
  run_id: "RUN-real",
  activation_id: "ACTIVATION-real",
  stage: "ACTIVE",
  message: "Reviewed candidate activated for impact analysis"
});

const resolving = run({
  run_id: "RUN-real",
  activation_id: "ACTIVATION-real",
  stage: "RESOLVING_IMPACT",
  message: "Resolving source and tracing downstream lineage through DataHub MCP"
});

const impact = run({
  run_id: "RUN-real",
  activation_id: "ACTIVATION-real",
  stage: "IMPACT_READY",
  message: "Five graph-derived responses are ready",
  decisions: [decision],
  source: {
    urn: summary.source_asset.urn,
    resolved_via: "DataHub MCP search plus exact URN validation",
    obligation_id: "ATLAS-LIC-004",
    active_version: 4
  },
  graph: {
    downstream_entity_count: 11,
    terminal_count: 1,
    read_interface: "mcp-server-datahub 0.6.0 live MCP"
  },
  unaffected_control: {
    asset_urn: "urn:control",
    display_name: "Unrelated Control Asset",
    native_type: "dataset",
    outside_affected_set_proof: "absent from DataHub MCP downstream lineage result",
    unmutated_verified: false,
    datahub_url: null
  }
});

describe("GateApiDataSource", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads a routed change by its exact identity", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", routeFetch(async (url) => {
      calls.push(url);
      return basicRoute(url);
    }));
    const source = new GateApiDataSource({
      baseUrl: "http://api",
      changeId: "CHANGE-real"
    });

    await expect(source.getChange()).resolves.toMatchObject({ change_id: "CHANGE-real" });
    expect(calls).toEqual(["http://api/api/changes/CHANGE-real"]);
  });

  it("polls the stable run concurrently and exposes no plan before IMPACT_READY", async () => {
    let impactReady = false;
    let finishImpact!: () => void;
    const impactGate = new Promise<void>((resolve) => { finishImpact = resolve; });
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url.endsWith("/api/changes")) return json([summary]);
      if (url.endsWith("/api/changes/CHANGE-real")) {
        return json({ summary, candidate: { rules: [] } });
      }
      if (url.endsWith("/activate")) return json(activation);
      if (url.endsWith("/impact")) {
        await impactGate;
        impactReady = true;
        return json(impact);
      }
      if (url.endsWith("/api/runs/RUN-real")) {
        return json(impactReady ? impact : resolving);
      }
      throw new Error(`Unexpected request: ${url}`);
    }));
    const source = new GateApiDataSource({
      baseUrl: "http://127.0.0.1:8013",
      pollIntervalMs: 1
    });
    const progress: RunProgressDTO[] = [];
    source.observeRun((event) => progress.push(event));

    const pending = source.activate();
    await waitFor(() => progress.some((event) => event.server_stage === "RESOLVING_IMPACT"));
    await expect(source.getImpactPlan()).rejects.toThrow("before derivation");
    const live = progress[progress.length - 1]!;
    expect(live.phase).toBe("resolving_impact");
    expect(live.server_message).toContain("tracing downstream lineage");
    expect(live.downstream_entity_count).toBeNull();
    expect(live.terminal_path_count).toBeNull();
    expect(live.terminals_revealed).toBe(0);
    expect(calls.some((value) => value.startsWith("POST ") && value.endsWith("/impact"))).toBe(true);
    expect(calls.some((value) => value.startsWith("GET ") && value.endsWith("/runs/RUN-real"))).toBe(true);

    finishImpact();
    await pending;
    const plan = await source.getImpactPlan();
    expect(plan.terminals).toHaveLength(1);
    expect(progress[progress.length - 1]?.server_stage).toBe("IMPACT_READY");
    expect(progress[progress.length - 1]?.phase).toBe("complete");
    expect(progress.map((event) => event.phase)).not.toEqual(
      expect.arrayContaining(["reconstructing_lineage", "reading_terminals", "deriving_responses"])
    );
  });

  it("cancels polling and rejects stale completion after navigation/reset", async () => {
    let finishImpact!: () => void;
    const impactGate = new Promise<void>((resolve) => { finishImpact = resolve; });
    vi.stubGlobal("fetch", routeFetch(async (url, init) => {
      if (url.endsWith("/activate")) return activation;
      if (url.endsWith("/impact")) {
        await impactGate;
        return impact;
      }
      if (url.endsWith("/runs/RUN-real")) return resolving;
      return basicRoute(url, init);
    }));
    const source = new GateApiDataSource({
      baseUrl: "http://127.0.0.1:8013",
      pollIntervalMs: 1
    });
    const pending = source.activate();
    await waitFor(() => true);
    source.cancelPending();
    finishImpact();
    await pending;
    await expect(source.getImpactPlan()).rejects.toThrow("before derivation");
  });

  it("retains only the newer operation when an older impact response arrives late", async () => {
    let activationCount = 0;
    let finishOld!: () => void;
    let finishNew!: () => void;
    const oldGate = new Promise<void>((resolve) => { finishOld = resolve; });
    const newGate = new Promise<void>((resolve) => { finishNew = resolve; });
    const oldActivation = run({ run_id: "RUN-old", activation_id: "ACT-old", stage: "ACTIVE", message: "old" });
    const newActivation = run({ run_id: "RUN-new", activation_id: "ACT-new", stage: "ACTIVE", message: "new" });
    const oldImpact = { ...impact, run_id: "RUN-old", activation_id: "ACT-old" };
    const newImpact = { ...impact, run_id: "RUN-new", activation_id: "ACT-new" };
    vi.stubGlobal("fetch", routeFetch(async (url, init) => {
      if (url.endsWith("/activate")) {
        activationCount += 1;
        return activationCount === 1 ? oldActivation : newActivation;
      }
      if (url.endsWith("/impact")) {
        if (activationCount === 1) {
          await oldGate;
          return oldImpact;
        }
        await newGate;
        return newImpact;
      }
      if (url.endsWith("/runs/RUN-old")) return oldActivation;
      if (url.endsWith("/runs/RUN-new")) return newImpact;
      return basicRoute(url, init);
    }));
    const source = new GateApiDataSource({ baseUrl: "http://api", pollIntervalMs: 1 });
    const old = source.activate();
    await waitFor(() => activationCount === 1);
    const newer = source.activate();
    await waitFor(() => activationCount === 2);
    finishNew();
    await newer;
    finishOld();
    await old;
    expect((await source.getImpactPlan()).run_id).toBe("RUN-new");
  });

  it("keeps one run/activation identity through recording and receipt retrieval", async () => {
    const receipt = verifiedReceipt();
    const verified = {
      ...impact,
      stage: "VERIFIED",
      decisions: [{ ...decision, readback_verified: true }],
      receipts: [receipt],
      reconciliation_verified: true
    };
    const calls: string[] = [];
    vi.stubGlobal("fetch", routeFetch(async (url, init) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url.endsWith("/api/runs")) return [impact];
      if (url.endsWith("/writeback")) return verified;
      if (url.endsWith("/writeback-progress")) {
        return writebackProgress("VERIFIED");
      }
      if (url.endsWith("/runs/RUN-real")) return verified;
      return basicRoute(url, init);
    }));
    const source = new GateApiDataSource({ baseUrl: "http://api" });
    await source.resumeImpact();
    const events: RecordingProgressDTO[] = [];
    source.observeRecording((event) => events.push(event));
    await source.recordProposedResponses(["churn_model_a"]);
    const receipts = await source.getReceipts();
    expect(events[events.length - 1]?.phase).toBe("reconciled");
    expect(receipts[0].response_identity).toBe(decision.decision_id);
    expect(calls).toContain("POST http://api/api/runs/RUN-real/writeback");
    expect(calls).toContain("GET http://api/api/runs/RUN-real");
  });

  it("keeps a backend READBACK_MISMATCH visible instead of emitting success", async () => {
    const mismatch = {
      ...impact,
      stage: "READBACK_MISMATCH",
      receipts: [verifiedReceipt()],
      reconciliation_verified: false
    };
    vi.stubGlobal("fetch", routeFetch(async (url, init) => {
      if (url.endsWith("/api/runs")) return [impact];
      if (url.endsWith("/writeback")) {
        return new Response(JSON.stringify({
          code: "READBACK_MISMATCH",
          message: "DataHub receipt readback did not reconcile",
          affected_set_produced: true,
          retryable: true
        }), { status: 503, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/writeback-progress")) {
        return writebackProgress("FAILED", {
          category: "READBACK_MISMATCH",
          safe_message: "DataHub receipt readback did not reconcile"
        });
      }
      if (url.endsWith("/runs/RUN-real")) return mismatch;
      return basicRoute(url, init);
    }));
    const source = new GateApiDataSource({ baseUrl: "http://api" });
    await source.resumeImpact();
    const recording: RecordingProgressDTO[] = [];
    const errors: ErrorProjectionDTO[] = [];
    source.observeRecording((event) => recording.push(event));
    source.observeErrors((error) => errors.push(error));
    await source.recordProposedResponses(["churn_model_a"]);
    expect(recording.some((event) => event.phase === "reconciled")).toBe(false);
    expect(recording[recording.length - 1]?.phase).toBe("partial");
    expect(errors[errors.length - 1]?.code).toBe("READBACK_MISMATCH");
  });

  it("emits row and counter progress from real polled entity phases", async () => {
    const receipt = verifiedReceipt();
    const verified = {
      ...impact,
      stage: "VERIFIED",
      decisions: [{ ...decision, readback_verified: true }],
      receipts: [receipt],
      reconciliation_verified: true
    };
    let progressCalls = 0;
    let finishWrite!: () => void;
    const writeGate = new Promise<void>((resolve) => {
      finishWrite = resolve;
    });
    vi.stubGlobal("fetch", routeFetch(async (url) => {
      if (url.endsWith("/api/runs")) return [impact];
      if (url.endsWith("/writeback")) {
        await writeGate;
        return verified;
      }
      if (url.endsWith("/writeback-progress")) {
        progressCalls += 1;
        if (progressCalls === 1) return writebackProgress("PENDING");
        if (progressCalls === 2) return writebackProgress("VERIFYING_MCP");
        finishWrite();
        return writebackProgress("VERIFIED");
      }
      return basicRoute(url);
    }));
    const source = new GateApiDataSource({
      baseUrl: "http://api",
      pollIntervalMs: 1
    });
    await source.resumeImpact();
    const recording: RecordingProgressDTO[] = [];
    source.observeRecording((event) => recording.push(event));

    await source.recordProposedResponses(["churn_model_a"]);

    expect(recording.map((event) => event.phase)).toEqual([
      "recording",
      "verifying_readbacks",
      "reconciled"
    ]);
    expect(
      recording.map((event) => event.readback_verified_count)
    ).toEqual([0, 0, 1]);
    expect(
      recording.map(
        (event) => event.entity_progress[0]?.phase
      )
    ).toEqual(["PENDING", "VERIFYING_MCP", "VERIFIED"]);
  });

  it("normalizes native entity links to their Properties tab", () => {
    expect(dataHubPropertiesUrl(
      "http://localhost:9002/tasks/urn:li:dataJob:(flow,job)/"
    )).toBe("http://localhost:9002/tasks/urn:li:dataJob:(flow,job)/Properties");
    expect(dataHubPropertiesUrl("javascript:alert(1)")).toBeNull();
  });

  it("rejects duplicate receipt identities even when the backend flag is true", () => {
    const receipt = verifiedReceipt();
    expect(isReconciled({
      ...impact,
      receipts: [receipt, receipt],
      reconciliation_verified: true
    })).toBe(false);
  });
});

function run(overrides: Record<string, unknown>): any {
  return {
    run_id: "RUN-real",
    change_id: summary.change_id,
    activation_id: "ACTIVATION-real",
    stage: "ACTIVE",
    progress: {
      stage: String(overrides.stage ?? "ACTIVE"),
      message: String(overrides.message ?? "active"),
      completed: 0,
      total: 5,
      error: null
    },
    source: null,
    graph: null,
    decisions: [],
    receipts: [],
    reconciliation_verified: false,
    unaffected_control: null,
    ...overrides
  };
}

function verifiedReceipt() {
  return {
    decision_id: decision.decision_id,
    asset_urn: decision.asset_urn,
    written: true,
    mcp_tag_readback_verified: true,
    sdk_receipt_readback_verified: true,
    stable_recorded_at: true,
    duplicate_tags: false,
    recorded_at: "2026-07-27T18:00:00Z",
    datahub_url: decision.datahub_url
  };
}

function writebackProgress(
  phase:
    | "PENDING"
    | "VERIFYING_MCP"
    | "VERIFIED"
    | "FAILED",
  failure: {
    category: "PARTIAL_WRITE" | "READBACK_MISMATCH";
    safe_message: string;
  } | null = null
) {
  const responseId = ["PENDING"].includes(phase)
    ? null
    : decision.decision_id;
  const entity = {
    entity_id: decision.decision_id,
    terminal_display_name: decision.display_name,
    sequence_index: 1,
    phase,
    phase_started_at: "2026-07-29T20:00:00Z",
    response_id: responseId,
    failure
  };
  return {
    run_id: "RUN-real",
    events: [entity],
    entities: [entity],
    terminal: phase === "VERIFIED" || phase === "FAILED",
    failed: phase === "FAILED"
  };
}

function json(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

function routeFetch(
  handler: (url: string, init?: RequestInit) => Promise<unknown>
) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const result = await handler(String(input), init);
    return result instanceof Response ? result : json(result);
  });
}

function basicRoute(url: string, _init?: RequestInit): unknown {
  if (url.endsWith("/api/changes")) return [summary];
  if (url.endsWith("/api/changes/CHANGE-real")) {
    return { summary, candidate: { rules: [] } };
  }
  throw new Error(`Unexpected request: ${url}`);
}

async function waitFor(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 200; attempt += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 1));
  }
  throw new Error("Timed out waiting for test condition.");
}
