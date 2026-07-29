import { chromium } from "playwright-core";

const baseUrl = process.env.COVENANT_FRONTEND_URL ?? "http://127.0.0.1:5173";
const executablePath = process.env.CHROME_PATH;
const screenshotDir = process.env.COVENANT_SCREENSHOT_DIR;

if (!executablePath) {
  throw new Error("CHROME_PATH is required for browser verification.");
}

const browser = await chromium.launch({
  executablePath,
  headless: true
});

const consoleErrors = [];
const pageErrors = [];
const requestFailures = [];
const responseFailures = [];

try {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "no-preference"
  });
  const page = await context.newPage();
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => {
    requestFailures.push(`${request.method()} ${request.url()} ${request.failure()?.errorText ?? ""}`);
  });
  page.on("response", (response) => {
    if (response.status() >= 400) {
      responseFailures.push(`${response.status()} ${response.url()}`);
    }
  });

  await page.goto(`${baseUrl}/changes`);
  await page.getByRole("heading", { name: "Data-use Changes" }).waitFor();
  await expectAbsent(page, "Churn Model A");
  await expectAbsent(page, "0 ●");

  await page.getByRole("button", { name: /Review change/ }).click();
  await page.waitForURL((url) => /^\/changes\/[^/]+$/.test(url.pathname));
  const changePathname = new URL(page.url()).pathname;
  await page.getByRole("heading", { name: /Atlas Signals v3 → v4/ }).waitFor();
  await expectAbsent(page, "Customer Delivery Job");
  await page
    .getByText(
      "Authorizes impact analysis only. Does not enact, approve, or execute the obligation change.",
      { exact: false }
    )
    .waitFor();
  await page.getByRole("button", { name: "Activate for impact analysis" }).waitFor();
  if (screenshotDir) {
    await page.screenshot({
      path: `${screenshotDir}/covenant-reviewed-activation-1440x900.png`,
      fullPage: false
    });
  }

  await page.getByRole("button", { name: "Activate for impact analysis" }).click();
  await page.waitForURL((url) => url.pathname === `${changePathname}/impact`);
  await page
    .getByLabel("Resolving impact through DataHub", { exact: true })
    .waitFor({ timeout: 10_000 });
  await page
    .getByText(/Resolving source and tracing downstream lineage through DataHub MCP/)
    .waitFor({ timeout: 10_000 });
  await expectAbsent(page, "Churn Model A");
  await expectAbsent(page, "Customer Delivery Job");
  await expectAbsent(page, "1 Allowed");
  await expectAbsent(page, "Reconstructing downstream lineage");
  await expectAbsent(page, "Classifying terminal uses");
  await expectAbsent(page, "Deriving proposed responses");
  if (screenshotDir) {
    await page.screenshot({
      path: `${screenshotDir}/covenant-processing-1440x900.png`,
      fullPage: false
    });
  }
  await page.getByText("Churn Model A", { exact: true }).first().waitFor({
    timeout: 45_000
  });
  await page
    .getByText(/Analysis complete · rendering five verified paths/)
    .first()
    .waitFor();
  const graphPath = page.locator(".graph-path-reveal").first();
  if ((await graphPath.evaluate((element) => getComputedStyle(element).animationName)) !== "graphPathReveal") {
    throw new Error("Completed graph did not use the presentation-only path reveal animation.");
  }
  await graphPath.evaluate((element) =>
    Promise.all(element.getAnimations().map((animation) => animation.finished))
  );
  await page.locator(".graph-path-reveal").first().waitFor({
    state: "detached",
    timeout: 5_000
  });
  if ((await page.locator('[aria-pressed="true"]').count()) !== 0) {
    throw new Error("Impact completion selected a terminal before the user chose one.");
  }
  await page.getByRole("button", { name: "Record 5 proposed responses in DataHub" }).waitFor();
  await page.getByLabel("1 Allowed").waitFor();
  await page.getByLabel("2 Remediate").waitFor();
  await page.getByLabel("1 Stop proposed").waitFor();
  await page.getByLabel("1 Governance review").waitFor();
  if (screenshotDir) {
    await page.screenshot({
      path: `${screenshotDir}/covenant-completed-1440x900.png`,
      fullPage: false
    });
  }
  await page.reload();
  await page.getByText("Churn Model A", { exact: true }).first().waitFor({
    timeout: 30_000
  });
  if ((await page.locator(".graph-path-reveal").count()) !== 0) {
    throw new Error("Completed graph replayed its first-view animation after reload.");
  }
  await page.getByRole("button", { name: "Record 5 proposed responses in DataHub" }).waitFor();
  await page.getByLabel("1 Allowed").waitFor();
  await page.getByLabel("2 Remediate").waitFor();
  if ((await page.locator('[aria-pressed="true"]').count()) !== 0) {
    throw new Error("Reloaded impact plan selected a terminal before the user chose one.");
  }
  await page.getByRole("button", { name: /Churn Model A, Remediate/ }).last().click();
  await page.getByText("machine-learning training is prohibited;", { exact: false }).first().waitFor();
  await page.getByText(/DataHub lineage path/).waitFor();
  await page.getByText("Evidence · Churn Model A", { exact: true }).scrollIntoViewIfNeeded();
  await page.getByText("Proposed response", { exact: true }).waitFor();
  await page.getByText("Why this disposition", { exact: true }).waitFor();
  if (screenshotDir) {
    await page.screenshot({
      path: `${screenshotDir}/covenant-evidence-1440x900.png`,
      fullPage: false
    });
  }
  await page.getByRole("button", { name: /Customer Delivery Job, Stop proposed/ }).last().click();
  await page.getByText(/not stopped/).first().waitFor();
  await page.getByRole("button", { name: /Anonymized Segment Derivative, Governance review/ }).last().click();
  await page.getByText(/Governance review required · unresolved/).first().waitFor();
  await page.getByText(/Outside affected set/, { exact: false }).waitFor();
  await expectAbsent(page, "verified unmutated");
  await page
    .getByText(
      "Records proposals only. Does not approve, execute, retrain, stop, or enforce.",
      { exact: true }
    )
    .waitFor();
  if (screenshotDir) {
    await page.screenshot({
      path: `${screenshotDir}/covenant-restraint-1440x900.png`,
      fullPage: false
    });
  }

  await page.getByRole("button", { name: "Record 5 proposed responses in DataHub" }).click();
  if ((await page.locator(".graph-path-reveal").count()) !== 0) {
    throw new Error("Graph reveal remained armed when writeback began.");
  }
  await page.waitForURL(/\/impact-plans\/RUN-/, { timeout: 45_000 });
  await page
    .getByText("5 proposed responses recorded in DataHub · 5 readbacks verified.", {
      exact: true
    })
    .waitFor();
  await page
    .getByText(/How verified · Verified by matching response IDs and target URNs across MCP tag and SDK receipt readbacks/)
    .waitFor();
  await page.getByText(/Outside affected set · verified unmutated/, { exact: false }).waitFor();
  const recordedUrl = page.url();
  const dataHubLinks = page.getByRole("link", { name: /properties in DataHub/ });
  if ((await dataHubLinks.count()) < 5) {
    throw new Error("Expected an inspectable DataHub link for every recorded target.");
  }
  const dataHubHrefs = [
    ...new Set(
      await dataHubLinks.evaluateAll((items) =>
        items.map((item) => item.getAttribute("href")).filter(Boolean)
      )
    )
  ];
  if (!dataHubHrefs.every((href) => href.endsWith("/Properties"))) {
    throw new Error("Recorded targets did not link directly to native Properties.");
  }
  const firstDataHubHref = await dataHubLinks.first().getAttribute("href");
  if (!firstDataHubHref?.startsWith("http://localhost:9002/")) {
    throw new Error("Recorded target did not expose the configured DataHub UI URL.");
  }
  const dataHubContext = await browser.newContext({
    viewport: { width: 1440, height: 900 }
  });
  const dataHubPage = await dataHubContext.newPage();
  await dataHubPage.goto(firstDataHubHref);
  const loginUser = dataHubPage.getByPlaceholder("Enter username");
  if (await loginUser.isVisible().catch(() => false)) {
    await loginUser.fill(process.env.DATAHUB_TEST_USERNAME ?? "datahub");
    await dataHubPage
      .locator('input[type="password"]')
      .fill(process.env.DATAHUB_TEST_PASSWORD ?? "datahub");
    await dataHubPage
      .getByRole("button", { name: "Login", exact: true })
      .click();
  }
  await dataHubPage
    .getByText("Internal Executive Dashboard", { exact: true })
    .first()
    .waitFor({ timeout: 30_000 });
  if (/404|page not found/i.test(await dataHubPage.locator("body").innerText())) {
    throw new Error(`DataHub target route did not resolve: ${firstDataHubHref}`);
  }
  const expectedDataHubTargets = [
    "Internal Executive Dashboard",
    "Churn Model A",
    "Propensity Model B",
    "Customer Delivery Job",
    "Anonymized Segment Derivative"
  ];
  for (const [index, href] of dataHubHrefs.entries()) {
    await dataHubPage.goto(href);
    await dataHubPage
      .getByText(expectedDataHubTargets[index], { exact: true })
      .first()
      .waitFor({ timeout: 30_000 });
    if (/404|page not found/i.test(await dataHubPage.locator("body").innerText())) {
      throw new Error(`DataHub target route did not resolve: ${href}`);
    }
  }
  const deliveryHref = dataHubHrefs.find((href) => href.includes("/tasks/"));
  if (!deliveryHref) {
    throw new Error("Customer Delivery Job Properties link was not exposed.");
  }
  await dataHubPage.goto(deliveryHref);
  await dataHubPage
    .getByText("Customer Delivery Job", { exact: true })
    .first()
    .waitFor({ timeout: 30_000 });
  const dispositionProperty = dataHubPage.getByText(
    "covenant.decision.disposition",
    { exact: true }
  );
  await dispositionProperty.waitFor();
  await dataHubPage.getByText("stop_proposed", { exact: true }).waitFor();
  await dataHubPage
    .getByText("human-authorized stop of synthetic redistribution workflow", {
      exact: true
    })
    .waitFor();
  await dataHubPage
    .getByText(/COV-ATLAS-LIC-004-v4-/)
    .last()
    .waitFor();
  await dispositionProperty.scrollIntoViewIfNeeded();
  if (screenshotDir) {
    await dataHubPage.screenshot({
      path: `${screenshotDir}/datahub-delivery-properties-1440x900.png`,
      fullPage: false
    });
  }
  await dataHubContext.close();
  await page.getByRole("button", { name: "Impact Plans" }).click();
  await page.waitForURL("**/impact-plans");
  await page.getByText(/Atlas Signals — Impact Plan/).waitFor();

  if (screenshotDir) {
    await page.goto(recordedUrl);
    await page
      .getByText("v3 → v4 · recorded · replay-stable", { exact: true })
      .first()
      .waitFor();
    await page.getByText(/vendor_demographics_raw/).first().waitFor();
    await expectAbsent(page, "pending resolution");
    await page.getByLabel("Recorded", { exact: true }).waitFor();
    await page.screenshot({
      path: `${screenshotDir}/covenant-receipt-1440x900.png`,
      fullPage: false
    });
  }

  const reduced = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "reduce"
  });
  const reducedPage = await reduced.newPage();
  reducedPage.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  reducedPage.on("pageerror", (error) => pageErrors.push(error.message));
  await reducedPage.goto(recordedUrl);
  await reducedPage.getByText("Churn Model A", { exact: true }).first().waitFor();
  const reducedPreference = await reducedPage.evaluate(() =>
    matchMedia("(prefers-reduced-motion: reduce)").matches
  );
  const transitionDuration = await reducedPage
    .getByRole("button", { name: /Churn Model A/ })
    .first()
    .evaluate((element) => getComputedStyle(element).transitionDuration);
  if (!reducedPreference || transitionDuration !== "0s") {
    throw new Error(
      `Reduced motion was not honored: preference=${reducedPreference}, transition=${transitionDuration}`
    );
  }
  await reduced.close();

  if (
    consoleErrors.length ||
    pageErrors.length ||
    requestFailures.length ||
    responseFailures.length
  ) {
    throw new Error(
      JSON.stringify(
        { consoleErrors, pageErrors, requestFailures, responseFailures },
        null,
        2
      )
    );
  }

  process.stdout.write(
    `${JSON.stringify(
      {
        routes: [
          "/changes",
          changePathname,
          `${changePathname}/impact`,
          "/impact-plans",
          new URL(recordedUrl).pathname
        ],
        viewport: "1440x900",
        reduced_motion: true,
        console_errors: 0,
        request_failures: 0,
        response_failures: 0,
        datahub_target_url: firstDataHubHref,
        datahub_climax_url: deliveryHref
      },
      null,
      2
    )}\n`
  );
  await context.close();
} finally {
  await browser.close();
}

async function expectAbsent(page, text) {
  if ((await page.getByText(text, { exact: false }).count()) !== 0) {
    throw new Error(`Unexpected pre-derivation content: ${text}`);
  }
}
