import { chromium } from "playwright-core";

const baseUrl =
  process.env.COVENANT_FRONTEND_URL ?? "http://127.0.0.1:5173";
const executablePath = process.env.CHROME_PATH;
if (!executablePath) {
  throw new Error("CHROME_PATH is required for browser verification.");
}

const browser = await chromium.launch({ executablePath, headless: true });

try {
  for (const viewport of [
    { name: "laptop", width: 1280, height: 800 },
    { name: "narrow", width: 390, height: 844 },
  ]) {
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    const failures = [];
    page.on("console", (message) => {
      if (message.type() === "error") failures.push(message.text());
    });
    page.on("pageerror", (error) => failures.push(error.message));
    await page.route("**/api/agreements/registered", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            vendor_id: "urn:li:covenantVendor:atlas-signals",
            vendor_name: "Atlas Signals",
            obligation_id: "ATLAS-LIC-004",
            current_version: "v3",
            effective_date: "2025-07-01T00:00:00Z",
            prior_document_path: "fixtures/atlas_license_v3.md",
          },
        ]),
      }),
    );
    await page.goto(`${baseUrl}/analyze`);
    await page
      .getByRole("heading", {
        name: "Analyze a governed agreement change",
      })
      .waitFor();

    const dimensions = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      content: document.documentElement.scrollWidth,
    }));
    if (dimensions.content > dimensions.viewport) {
      throw new Error(
        `${viewport.name} has horizontal overflow: ${JSON.stringify(dimensions)}`,
      );
    }

    const select = page.getByRole("button", { name: "Select document" });
    await select.focus();
    const focusStyle = await select.evaluate((element) => {
      const style = getComputedStyle(element);
      return {
        outlineStyle: style.outlineStyle,
        outlineWidth: style.outlineWidth,
        boxShadow: style.boxShadow,
      };
    });
    if (
      (focusStyle.outlineStyle === "none" ||
        focusStyle.outlineWidth === "0px") &&
      focusStyle.boxShadow === "none"
    ) {
      throw new Error(
        `${viewport.name} Select document has no visible keyboard focus.`,
      );
    }
    await page.keyboard.press("Enter");
    if (
      !(await page
        .locator('input[type="file"][aria-label="Select candidate agreement"]')
        .count())
    ) {
      throw new Error(`${viewport.name} file input lacks its accessible name.`);
    }
    if (failures.length) {
      throw new Error(`${viewport.name} browser failures: ${failures.join("; ")}`);
    }
    await context.close();
  }
  console.log("Beat 0 responsive and keyboard checks passed.");
} finally {
  await browser.close();
}
