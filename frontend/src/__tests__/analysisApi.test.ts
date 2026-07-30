import { afterEach, describe, expect, it, vi } from "vitest";

import { AnalysisApi, AnalysisApiError } from "../adapter/AnalysisApi";

const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json" },
  });

describe("Beat 0 API adapter", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses the real registered-agreement and match endpoints", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        calls.push({ url, init });
        if (url.endsWith("/api/agreements/registered")) return json([]);
        if (url.endsWith("/api/analyses/match")) {
          return json({
            match_id: "MATCH-real",
            stream_url: "/analyses/MATCH-real/events",
          });
        }
        throw new Error(`unexpected ${url}`);
      }),
    );
    const api = new AnalysisApi("http://api");
    await expect(api.registered()).resolves.toEqual([]);
    const file = new File(["agreement"], "atlas.pdf", {
      type: "application/pdf",
    });
    await expect(api.startMatch(file)).resolves.toMatchObject({
      match_id: "MATCH-real",
    });
    expect(calls[0]?.url).toBe(
      "http://api/api/agreements/registered",
    );
    expect(calls[1]?.url).toBe("http://api/api/analyses/match");
    expect(calls[1]?.init?.method).toBe("POST");
    expect(calls[1]?.init?.body).toBeInstanceOf(FormData);
  });

  it("calls extraction separately and preserves safe API errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/extract")) {
          return json(
            {
              code: "EXTRACTION_FAILED",
              message: "Bedrock extraction failed; no candidate was produced",
              retryable: true,
            },
            502,
          );
        }
        throw new Error(`unexpected ${url}`);
      }),
    );
    const api = new AnalysisApi("http://api");
    await expect(api.extract("MATCH-real")).rejects.toMatchObject({
      name: "Error",
      code: "EXTRACTION_FAILED",
      retryable: true,
      message: "Bedrock extraction failed; no candidate was produced",
    } satisfies Partial<AnalysisApiError>);
  });
});
