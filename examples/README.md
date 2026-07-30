# Covenant sample outputs

These are sanitized representative outputs from successful local runs of the fictional Atlas Signals / Northstar Commerce scenario. They let reviewers inspect the evidence contracts without running DataHub or Amazon Bedrock.

| File | What it demonstrates |
|---|---|
| [`candidate-delta.json`](candidate-delta.json) | Claude's structured, cited four-rule proposal before deterministic verification. This artifact is from the earlier canonical Markdown extraction. |
| [`verified-candidate.json`](verified-candidate.json) | The PDF-backed candidate after schema, hash, citation, date, vocabulary, evidence, and version checks pass. |
| [`match-result.json`](match-result.json) | One Bedrock tool-use lookup against the DataHub-native governed-agreement registry, followed by deterministic identity verification. |
| [`impact-plan.json`](impact-plan.json) | The live-MCP-derived affected paths and the canonical deterministic dispositions. |
| [`writeback-readback.json`](writeback-readback.json) | Five proposed responses written to native DataHub assets and verified through MCP tags plus SDK property readback. |

The screenshots show the verified PDF candidate, the graph-derived impact plan, and a native DataHub property page after writeback.

All companies, agreements, entities, owners, and URNs are synthetic. Run-specific timestamps, latency, retries, and token counts were omitted. Hash-derived IDs and fixture hashes are retained where they demonstrate traceability. Ignored local `smoke-test/` evidence references were changed to their public `examples/` equivalents.

Bedrock/Claude proposes matching and extraction; deterministic validation decides whether evidence is eligible for review. Live DataHub MCP and the DataHub SDK provide graph evidence, native writeback, and readback. “Recorded” means a proposed response was stored and verified—it does not mean an asset was stopped, retrained, approved, or otherwise acted upon.

The separate **SYNTHETIC TEST APPROVAL** transition is test-only and is intentionally excluded from the base writeback example.
