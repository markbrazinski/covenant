import { mkdir } from "node:fs/promises";
import { chromium } from "playwright-core";

const baseUrl =
  process.env.COVENANT_FRONTEND_URL ?? "http://127.0.0.1:5173";
const executablePath = process.env.CHROME_PATH;
const screenshotDir = process.env.COVENANT_SCREENSHOT_DIR;
if (!executablePath) {
  throw new Error("CHROME_PATH is required for browser verification.");
}
if (screenshotDir) await mkdir(screenshotDir, { recursive: true });

const browser = await chromium.launch({ executablePath, headless: true });

try {
  await runNoMatch();
  await runRejected();
  await runTimeout();
  console.log("Beat 0 failure browser checks passed.");
} finally {
  await browser.close();
}

async function runNoMatch() {
  const { context, page, failures } = await scenarioPage({
    matchId: "MATCH-no-match",
    matchEvents: [
      ev(1, "MATCH_STARTED"),
      ev(2, "IDENTIFYING_VENDOR"),
      ev(3, "TOOL_CALLED", {
        vendor_name_sent: "Unknown Vendor",
        obligation_id_sent: "UNKNOWN-LIC-999",
      }),
      ev(4, "TOOL_RETURNED", { status: "NOT_FOUND" }),
      ev(5, "MATCH_VERIFYING"),
      ev(6, "MATCH_NOT_FOUND"),
    ],
    matchDetail: matchDetail({
      matchId: "MATCH-no-match",
      phase: "MATCH_NOT_FOUND",
      vendor: "Unknown Vendor",
      obligation: "UNKNOWN-LIC-999",
      agreement: null,
    }),
  });
  await upload(page, "unknown.pdf");
  await page
    .getByRole("heading", { name: "Agreement not recognized" })
    .waitFor();
  await page.getByText(/Unknown Vendor · UNKNOWN-LIC-999/).waitFor();
  await page.getByText("→ NOT_FOUND", { exact: true }).waitFor();
  await capture(page, "beat0-06-no-match.png");
  assertClean(failures);
  await context.close();
}

async function runRejected() {
  const rejection = {
    rule_id: "R-003",
    check: "citation_verification",
    message: "Rule citation is not a byte-for-byte source substring.",
  };
  const { context, page, failures } = await scenarioPage({
    matchId: "MATCH-rejected",
    matchEvents: verifiedMatchEvents(),
    matchDetail: matchDetail({
      matchId: "MATCH-rejected",
      phase: "MATCH_VERIFIED",
    }),
    extractionEvents: [
      ev(1, "PREPARING_SOURCES"),
      ev(2, "EXTRACTING_BEDROCK"),
      ev(3, "MODEL_OUTPUT_RECEIVED"),
      ev(4, "VERIFYING_SCHEMA"),
      ev(5, "VERIFYING_CITATIONS_AND_RULES"),
      ev(6, "VERIFYING_CANDIDATE_CONSISTENCY"),
      ev(7, "VERIFICATION_COMPLETED", {
        status: "REJECT",
        failure_count: 1,
      }),
      ev(8, "EXTRACTION_REJECTED", { failures: [rejection] }),
    ],
    extractResponse: {
      change_id: null,
      candidate: {
        lifecycle_state: "REJECTED",
        rules: [],
        verification: { status: "REJECT", failures: [rejection] },
      },
      verification: { status: "REJECT", failures: [rejection] },
      persisted: false,
    },
  });
  await upload(page, "citation-challenge.pdf");
  await page
    .getByRole("heading", {
      name: "Candidate rejected by deterministic verification",
    })
    .waitFor();
  await page
    .getByText("R-003 · citation_verification", { exact: true })
    .waitFor();
  await page
    .getByText(
      "Rule citation is not a byte-for-byte source substring.",
      { exact: true },
    )
    .waitFor();
  await capture(page, "beat0-05-rejected.png");
  assertClean(failures);
  await context.close();
}

async function runTimeout() {
  const { context, page, failures } = await scenarioPage({
    matchId: "MATCH-timeout",
    matchEvents: verifiedMatchEvents(),
    matchDetail: matchDetail({
      matchId: "MATCH-timeout",
      phase: "MATCH_VERIFIED",
    }),
    extractionEvents: [
      ev(1, "PREPARING_SOURCES"),
      ev(2, "EXTRACTING_BEDROCK"),
      ev(3, "EXTRACTION_FAILED", {
        failure_category: "TIMEOUT",
        message: "Bedrock extraction failed; no candidate was produced",
      }),
    ],
    extractStatus: 502,
    extractResponse: {
      code: "EXTRACTION_FAILED",
      message: "Bedrock extraction failed; no candidate was produced",
      retryable: true,
    },
  });
  await upload(page, "timeout.pdf");
  await page
    .getByRole("heading", { name: "Analysis could not complete" })
    .waitFor();
  await page
    .getByText("Bedrock did not respond within 30 seconds.", {
      exact: true,
    })
    .waitFor();
  await page
    .getByRole("button", { name: "Retry extraction" })
    .waitFor();
  await capture(page, "beat0-07-extraction-error.png");
  failures.console = failures.console.filter(
    (message) =>
      !message.includes(
        "the server responded with a status of 502 (Bad Gateway)",
      ),
  );
  assertClean(failures, [502]);
  await context.close();
}

async function scenarioPage(scenario) {
  const failures = {
    console: [],
    page: [],
    requests: [],
    responses: [],
  };
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();
  page.on("console", (message) => {
    if (message.type() === "error") failures.console.push(message.text());
  });
  page.on("pageerror", (error) => failures.page.push(error.message));
  page.on("requestfailed", (request) =>
    failures.requests.push(`${request.method()} ${request.url()}`),
  );
  page.on("response", (response) => {
    if (response.status() >= 400) failures.responses.push(response.status());
  });
  await page.route("http://127.0.0.1:8001/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/agreements/registered") {
      return fulfillJson(route, [agreement()]);
    }
    if (url.pathname === "/api/analyses/match") {
      return fulfillJson(route, {
        match_id: scenario.matchId,
        stream_url: `/analyses/${scenario.matchId}/events`,
      });
    }
    if (
      url.pathname ===
      `/api/analyses/${scenario.matchId}/events`
    ) {
      return fulfillSse(route, scenario.matchEvents);
    }
    if (
      url.pathname ===
      `/api/analyses/${scenario.matchId}/extraction-events`
    ) {
      return fulfillSse(route, scenario.extractionEvents ?? []);
    }
    if (
      url.pathname === `/api/analyses/${scenario.matchId}/extract`
    ) {
      return fulfillJson(
        route,
        scenario.extractResponse ?? {},
        scenario.extractStatus ?? 200,
      );
    }
    if (url.pathname === `/api/analyses/${scenario.matchId}`) {
      return fulfillJson(route, scenario.matchDetail);
    }
    throw new Error(`Unmocked Beat 0 API request: ${url.pathname}`);
  });
  await page.goto(`${baseUrl}/analyze`);
  await page
    .getByText("Covenant currently governs 1 agreement.", { exact: true })
    .waitFor();
  return { context, page, failures };
}

async function upload(page, name) {
  await page.locator('input[type="file"]').setInputFiles({
    name,
    mimeType: "application/pdf",
    buffer: Buffer.from("# synthetic browser test agreement"),
  });
}

function verifiedMatchEvents() {
  return [
    ev(1, "MATCH_STARTED"),
    ev(2, "IDENTIFYING_VENDOR"),
    ev(3, "TOOL_CALLED", {
      vendor_name_sent: "Atlas Signals",
      obligation_id_sent: "ATLAS-LIC-004",
    }),
    ev(4, "TOOL_RETURNED", { status: "MATCH" }),
    ev(5, "MATCH_VERIFYING"),
    ev(6, "MATCH_VERIFIED"),
  ];
}

function matchDetail({
  matchId,
  phase,
  vendor = "Atlas Signals",
  obligation = "ATLAS-LIC-004",
  agreement: matched = agreement(),
}) {
  return {
    match_id: matchId,
    phase,
    events: [],
    result: {
      extracted_vendor_name: vendor,
      extracted_obligation_id: obligation,
      tool_call: {
        tool_result_status: matched ? "MATCH" : "NOT_FOUND",
        tool_result_match: matched,
      },
      match_metadata: {
        model_id: "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
      },
    },
    verification: { status: "PASS" },
    receipt: {},
    change_id: null,
    extraction_phase: null,
    extraction_events: [],
  };
}

function agreement() {
  return {
    vendor_id: "urn:li:covenantVendor:atlas-signals",
    vendor_name: "Atlas Signals",
    obligation_id: "ATLAS-LIC-004",
    current_version: "v3",
    effective_date: "2025-07-01T00:00:00Z",
    prior_document_path: "fixtures/atlas_license_v3.md",
  };
}

function ev(sequence, phase, data = {}) {
  return { sequence, phase, ...data };
}

async function fulfillJson(route, value, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(value),
  });
}

async function fulfillSse(route, events) {
  await route.fulfill({
    status: 200,
    contentType: "text/event-stream",
    body:
      events
        .map(
          (event) =>
            `id: ${event.sequence}\nevent: ${event.phase}\ndata: ${JSON.stringify(
              event,
            )}\n\n`,
        )
        .join(""),
  });
}

async function capture(page, filename) {
  if (!screenshotDir) return;
  await page.screenshot({
    path: `${screenshotDir}/${filename}`,
    fullPage: true,
  });
}

function assertClean(failures, allowedResponses = []) {
  const unexpectedResponses = failures.responses.filter(
    (status) => !allowedResponses.includes(status),
  );
  if (
    failures.console.length ||
    failures.page.length ||
    failures.requests.length ||
    unexpectedResponses.length
  ) {
    throw new Error(
      JSON.stringify(
        { ...failures, responses: unexpectedResponses },
        null,
        2,
      ),
    );
  }
}
