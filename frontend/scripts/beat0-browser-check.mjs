import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium } from "playwright-core";

const baseUrl =
  process.env.COVENANT_FRONTEND_URL ?? "http://127.0.0.1:5173";
const executablePath = process.env.CHROME_PATH;
const screenshotDir = process.env.COVENANT_SCREENSHOT_DIR;
const fixturePath = resolve(
  process.env.COVENANT_BEAT0_DOCUMENT ??
    "../fixtures/atlas_license_v4.md",
);

if (!executablePath) {
  throw new Error("CHROME_PATH is required for browser verification.");
}
if (screenshotDir) await mkdir(screenshotDir, { recursive: true });

const browser = await chromium.launch({ executablePath, headless: true });
const consoleErrors = [];
const pageErrors = [];
const requestFailures = [];
const responseFailures = [];

try {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "no-preference",
  });
  const page = await context.newPage();
  await page.addInitScript(() => {
    const NativeEventSource = window.EventSource;
    window.EventSource = class CovenantObservedEventSource extends NativeEventSource {
      constructor(url, options) {
        super(url, options);
        this.addEventListener("MATCH_VERIFIED", () => {
          const timing = window.__covenantBeat0Timing;
          if (timing && !timing.observed.matchVerified) {
            timing.observed.matchVerified =
              performance.now() - timing.startedAt;
          }
        });
      }
    };
  });
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => {
    requestFailures.push(
      `${request.method()} ${request.url()} ${
        request.failure()?.errorText ?? ""
      }`,
    );
  });
  page.on("response", (response) => {
    if (response.status() >= 400) {
      responseFailures.push(`${response.status()} ${response.url()}`);
    }
  });

  await page.goto(`${baseUrl}/analyze`);
  await page
    .getByRole("heading", {
      name: "Analyze a governed agreement change",
    })
    .waitFor();
  await page
    .getByText("Covenant currently governs 1 agreement.", { exact: true })
    .waitFor({ timeout: 20_000 });
  await page
    .getByText("No activity yet. Upload an agreement to begin.", {
      exact: true,
    })
    .waitFor();
  await capture(page, "beat0-01-landing.png");

  await page.evaluate(() => {
    const startedAt = performance.now();
    const observed = {};
    const record = () => {
      const text = document.body.innerText;
      const normalized = text.toLowerCase();
      if (!observed.matching && text.includes("Matching agreement")) {
        observed.matching = performance.now() - startedAt;
      }
      if (
        !observed.matched &&
        normalized.includes("matched to governed agreement")
      ) {
        observed.matched = performance.now() - startedAt;
      }
      if (
        !observed.extracting &&
        text.includes("Extracting via Bedrock")
      ) {
        observed.extracting = performance.now() - startedAt;
      }
      if (
        !observed.verified &&
        text.includes("Candidate verified and ready for review")
      ) {
        observed.verified = performance.now() - startedAt;
      }
    };
    window.__covenantBeat0Timing = { startedAt, observed };
    new MutationObserver(record).observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    record();
  });
  await page
    .locator('input[type="file"]')
    .setInputFiles(fixturePath);
  await page.waitForURL(/\/analyze\/MATCH-/);
  await page
    .locator(".analysis-status")
    .filter({ hasText: "Matching agreement" })
    .waitFor({ timeout: 10_000 });
  await page
    .getByText("Registry lookup", { exact: true })
    .waitFor({ timeout: 30_000 });
  await capture(page, "beat0-02-matching.png");

  await page
    .locator(".analysis-status")
    .filter({ hasText: "Extracting via Bedrock" })
    .waitFor({ timeout: 40_000 });
  await page
    .getByText("Matched to governed agreement", { exact: true })
    .waitFor();
  await page
    .getByText("effective 2025-07-01", { exact: false })
    .first()
    .waitFor();
  await capture(page, "beat0-03-extracting.png");

  await page
    .getByRole("heading", {
      name: "Candidate verified and ready for review",
    })
    .waitFor({ timeout: 45_000 });
  await page
    .getByText(
      "4 rules extracted from Atlas Signals v3 → v4. 4 citations verified against source.",
      { exact: true },
    )
    .waitFor();
  await page
    .getByText("→ 4 rules extracted · 4 citations verified", {
      exact: true,
    })
    .waitFor();
  const timing = await page.evaluate(() => {
    const values = window.__covenantBeat0Timing.observed;
    return {
      landing_to_matching_ms: Math.round(values.matching),
      match_phase_ms: Math.round(values.matchVerified - values.matching),
      match_to_extract_ms: Math.round(
        values.extracting - values.matchVerified,
      ),
      matched_card_lag_ms: Math.round(
        values.matched - values.matchVerified,
      ),
      extract_phase_ms: Math.round(values.verified - values.extracting),
      total_to_verified_ms: Math.round(values.verified),
    };
  });
  console.log(`BEAT0_TIMING ${JSON.stringify(timing)}`);
  await capture(page, "beat0-04-verified.png");

  const pulseAnimation = await page.evaluate(() => {
    const phase = document.createElement("div");
    phase.className = "analysis-phase analysis-phase--active";
    const pulse = document.createElement("span");
    pulse.className = "analysis-phase-dot";
    phase.append(pulse);
    document.body.append(phase);
    const style = getComputedStyle(pulse);
    const result = {
      duration: style.animationDuration,
      iterations: style.animationIterationCount,
    };
    phase.remove();
    return result;
  });
  if (
    pulseAnimation.duration !== "0.42s" ||
    pulseAnimation.iterations === "infinite"
  ) {
    throw new Error(
      `Unexpected Beat 0 pulse contract: ${JSON.stringify(pulseAnimation)}`,
    );
  }

  const stickyPosition = await page.evaluate(async () => {
    const maximum = document.documentElement.scrollHeight - innerHeight;
    scrollTo(0, Math.min(300, Math.max(0, maximum / 2)));
    await new Promise((resolve) => requestAnimationFrame(resolve));
    const panel = document.querySelector(".analysis-activity-column");
    return {
      scrollY,
      top: panel?.getBoundingClientRect().top ?? null,
    };
  });
  if (
    stickyPosition.scrollY > 56 &&
    (stickyPosition.top === null ||
      Math.abs(stickyPosition.top - 24) > 2)
  ) {
    throw new Error(
      `Agent activity panel did not remain sticky: ${JSON.stringify(
        stickyPosition,
      )}`,
    );
  }

  await page
    .getByRole("button", { name: "Continue to review" })
    .click();
  await page.waitForURL(/\/changes\/CHANGE-/);
  await page
    .getByRole("heading", { name: /Atlas Signals v3 → v4/ })
    .waitFor();
  const reviewScrollY = await page.evaluate(() => scrollY);
  if (reviewScrollY !== 0) {
    throw new Error(
      `Continue to review did not reset scroll: ${reviewScrollY}`,
    );
  }

  const reduced = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "reduce",
  });
  const reducedPage = await reduced.newPage();
  await reducedPage.goto(`${baseUrl}/analyze`);
  await reducedPage
    .getByRole("heading", {
      name: "Analyze a governed agreement change",
    })
    .waitFor();
  const reducedPreference = await reducedPage.evaluate(() =>
    matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  if (!reducedPreference) {
    throw new Error("Reduced-motion browser preference was not active.");
  }
  const reducedAnimations = await reducedPage.evaluate(() => {
    const phase = document.createElement("div");
    phase.className = "analysis-phase analysis-phase--active";
    const pulse = document.createElement("span");
    pulse.className = "analysis-phase-dot";
    phase.append(pulse);
    const card = document.createElement("section");
    card.className = "analysis-matched-card";
    document.body.append(phase, card);
    const result = {
      pulse: getComputedStyle(pulse).animationName,
      card: getComputedStyle(card).animationName,
    };
    phase.remove();
    card.remove();
    return result;
  });
  if (
    reducedAnimations.pulse !== "none" ||
    reducedAnimations.card !== "none"
  ) {
    throw new Error(
      `Reduced motion did not disable Beat 0 animations: ${JSON.stringify(
        reducedAnimations,
      )}`,
    );
  }
  await reduced.close();
  await context.close();

  if (
    consoleErrors.length ||
    pageErrors.length ||
    requestFailures.length ||
    responseFailures.length
  ) {
    throw new Error(
      JSON.stringify(
        {
          consoleErrors,
          pageErrors,
          requestFailures,
          responseFailures,
        },
        null,
        2,
      ),
    );
  }
  console.log("Beat 0 browser check passed.");
} finally {
  await browser.close();
}

async function capture(page, filename) {
  if (!screenshotDir) return;
  await page.screenshot({
    path: `${screenshotDir}/${filename}`,
    fullPage: false,
  });
}
