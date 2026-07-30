# Covenant Instructions for Claude

`AGENTS.md` is the repository's authoritative operating contract. Read it in
full before making changes. This file is a Claude-facing summary and must remain
semantically aligned with it; if the two files differ, follow `AGENTS.md`.

## Product truth

Covenant turns a reviewed source-data obligation change into a graph-derived
operational response plan.

The canonical verified result is:

- 1 allowed;
- 2 remediate;
- 1 stop proposed;
- 1 human review; and
- 1 unaffected.

DataHub must remain load-bearing. Live MCP derives the governed source,
affected-set membership, and exact lineage paths. The official SDK may read
usage/custom properties only after MCP supplies the affected URNs, and it
performs native writeback plus detailed receipt readback.

Never route by asset name, URN fragment, native type, branch, fixture position,
or expected-output list.

## Authority and evidence

- The supported model path is bounded Bedrock/Claude matching and extraction for
  fictional versioned clauses, followed by deterministic verification. Do not
  claim broad legal or contract interpretation.
- Candidate evidence must validate before review.
- Review and activation are distinct.
- Automated activation must use the literal **SYNTHETIC TEST APPROVAL** label
  and a visibly synthetic actor.
- `STOP_PROPOSED` is a proposal. Covenant does not stop pipelines.
- Covenant does not make legal determinations, approve ambiguous use, retrain
  models, perform machine unlearning, or contact external parties.
- MCP or DataHub failure must produce an unavailable state with no fabricated or
  cached affected plan presented as fresh evidence.
- Partial writeback must remain visibly partial until retry and readback
  reconcile all five receipts.

## Current project state

- Gates through 6D are merged on `main`.
- The React browser experience, Bedrock/Claude matching and extraction,
  deterministic verifier, DataHub-native agreement registry, MCP-derived impact
  plan, and native writeback/readback are implemented.
- Gate 7 is limited to submission documentation and sanitized evidence. Do not
  change production code, dependencies, or repository structure beyond its
  explicit commission.

When the local ignored documentation is present, read it before newly authorized
gate work:

```text
docs/Covenant_Handoff_2026-07-23.md
docs/commissions/Covenant_Winning_Project_Plan.md
docs/gates/gate-3-report.md
docs/gates/gate-4-report.md
```

These files are intentionally ignored and local.

## Supported commands

Backend reset/reseed verification:

```bash
cp .env.example .env
./scripts/bootstrap_runtime.sh
./scripts/run_verified_loop.sh
```

Gate 3 API while preserving an existing graph:

```bash
./scripts/start_covenant.sh
```

Then, from another terminal:

```bash
./scripts/run_verified_demo.sh
```

The default API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

Start the React frontend separately and open the judge flow at:

```text
http://127.0.0.1:5173/analyze
```

Do not silently substitute one operator path for another:

- `run_verified_loop.sh` intentionally resets and reseeds;
- `start_covenant.sh` preserves existing graph state and seeds only if absent.
- `run_verified_demo.sh` replays the existing canonical change and does not run
  the Bedrock upload/match/extraction flow.

## Repository and privacy rules

- Preserve all unrelated tracked and untracked user work.
- Never reset, clean, overwrite, or stage unrelated files to make the tree look
  clean.
- Never commit `.env`, credentials, tokens, private endpoints, machine
  identifiers, raw exports, real customer data, or unsanitized evidence.
- Gate reports, handoffs, commissions, and `smoke-test/` remain ignored, local,
  and owner-only. Tracked design references and sanitized `examples/` assets are
  explicit public exceptions.
- Tracked runtime code must not depend on ignored files.
- Sanitize generated logs, JUnit XML, screenshots, and recordings before
  preservation or staging.
- Do not create a remote, push, publish, deploy, or create paid resources without
  explicit owner approval.

## Scope control

Unless the current owner commission expressly authorizes it, do not add:

- new frontend product scope;
- another model provider or local model download;
- hosting;
- authentication or tenancy;
- Slack, Jira, email, or ticketing;
- automatic enforcement;
- broad document ingestion/OCR;
- production integrations; or
- machine-unlearning claims or behavior.

When a commission does authorize one of these areas, implement only its named
acceptance criteria and preserve all existing evidence, MCP causality, human
authority, replay, privacy, and unaffected-control invariants.
