# Covenant Repository Instructions

## Verified runtime contract

Covenant tests this thesis: when a source-data obligation changes, DataHub determines which downstream uses remain allowed, must stop, require remediation, or require a human decision, and Covenant records the response without touching unaffected assets.

The canonical result is exactly **1 allowed / 2 remediate / 1 stop proposed / 1 human review / 1 unaffected**. Covenant uses native DataHub Dashboard, MLModel, DataFlow, and DataJob entities. DataHub MCP lineage must derive the affected set and defensible paths; no hidden graph or terminal outcome keyed by an asset name, URN, branch, or list position is acceptable. Prefer deterministic policy logic.

The supported runtime is the official local DataHub Quickstart pinned to v1.6.0. It is a reproducible local judge path, not a hosted-access or production-readiness claim. Bootstrap and replay must use the committed scripts and remain idempotent.

Gate 2's supported extraction surface is deliberately bounded to literal,
versioned synthetic clauses. Candidate evidence must validate before review,
activation must be a separate event, and automated activation must use the
literal **SYNTHETIC TEST APPROVAL** label. Active candidate rules may supply
policy semantics, but live MCP remains the only affected-set and path source.

Gate 3's API is an orchestration boundary over those verified semantics. It must
keep candidate analysis, activation, MCP impact, and native writeback as distinct
states; project unavailable and partial outcomes truthfully; persist only ignored
local run state; and never accept expected terminal lists or dispositions from a
client.

Humans retain legal and governance authority. System recommendations and real human approvals are separate states. A fixture actor may exercise approval behavior only when every representation says **SYNTHETIC TEST APPROVAL**; never imply that a synthetic approval is real.

## Current gate state

- Gate 3 is complete at commit `d16ce34`; the last full verification recorded
  39 tests with zero failures.
- Gate 4 model-proposal evaluation is closed with `DEFER`. No approved model
  credential or local model runtime exists, and no model-backed capability may
  be claimed.
- Gate 5, the web experience, is the next planned product gate but is not
  authorized by this file. Begin it only after an explicit owner instruction.
- Reopening Gate 4 requires explicit provider/model, credential source,
  document-transmission permission, and cost/request or local-download approval.
- When the local ignored documentation is present, read
  `docs/Covenant_Handoff_2026-07-23.md` and the current gate report before
  beginning a newly authorized gate.

An explicit owner commission may authorize work otherwise excluded below, but
only within that commission's named scope. A broad request to “continue” does
not authorize publication, paid resources, real approval, external actions, or
productionization.

## Verified operator paths

Use the committed scripts rather than inventing alternate setup paths:

```bash
cp .env.example .env
./scripts/bootstrap_runtime.sh
./scripts/run_verified_loop.sh
```

For the Gate 3 API without silently resetting an existing graph:

```bash
./scripts/start_covenant.sh
./scripts/run_verified_demo.sh
```

`run_verified_loop.sh` is an intentional reset/reseed verification path.
`start_covenant.sh` preserves an existing graph and seeds only when the canonical
source is absent. Do not blur these behaviors.

## Scope and safety

- Unless a current explicit commission authorizes it, do not build a frontend,
  model integration, hosted service, Slack or Jira integration, broad contract
  parser, production integration, or machine-unlearning feature or claim.
- Even when a frontend is authorized, bind it to the real Gate 3 API; do not
  hardcode expected terminals, paths, dispositions, receipts, or success states.
- Treat existing tracked and untracked changes as user work. Preserve unrelated
  files and never clean, reset, overwrite, or stage them merely to obtain a
  clean status.
- Never put secrets, raw environment identifiers, private endpoints, account data, raw exports, or credentials in tracked files.
- Sanitize generated evidence before staging; visually inspect any evidence screenshot before copying it into `smoke-test/screenshots/`.
- Record commands, exact versions, results, limitations, and deviations while work proceeds.
- Do not create a remote or push without explicit owner approval.
- Do not publish, create a remote, or begin a later gate without explicit owner approval.

Gate commissions, reports, and handoffs remain local under ignored `docs/`;
generated evidence and API run state remain under ignored `smoke-test/`. Tracked
runtime code must not depend on either ignored directory. Any contradiction
between implementation convenience and the current commission resolves in favor
of truth, privacy, human authority, and the acceptance criteria.
