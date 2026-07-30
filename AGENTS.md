# Covenant Repository Instructions

## Verified runtime contract

Covenant tests this thesis: when a source-data obligation changes, DataHub determines which downstream uses remain allowed, must stop, require remediation, or require a human decision, and Covenant records the response without touching unaffected assets.

The canonical result is exactly **1 allowed / 2 remediate / 1 stop proposed / 1 human review / 1 unaffected**. Covenant uses native DataHub Dashboard, MLModel, DataFlow, and DataJob entities. DataHub MCP lineage must derive the affected set and defensible paths; no hidden graph or terminal outcome keyed by an asset name, URN, branch, or list position is acceptable. Prefer deterministic policy logic.

The supported runtime is the official local DataHub Quickstart pinned to v1.6.0. It is a reproducible local judge path, not a hosted-access or production-readiness claim. Bootstrap and replay must use the committed scripts and remain idempotent.

The supported extraction surface is deliberately bounded to versioned synthetic
clauses. Bedrock/Claude may propose agreement matches and cited candidate rules,
but deterministic verification controls evidence eligibility. Candidate
evidence must validate before review, activation must be a separate event, and
automated activation must use the literal **SYNTHETIC TEST APPROVAL** label.
Active candidate rules may supply policy semantics, but live MCP remains the
only affected-set and path source.

The API is an orchestration boundary over those verified semantics. It must
keep candidate analysis, activation, MCP impact, and native writeback as distinct
states; project unavailable and partial outcomes truthfully; persist only ignored
local run state; and never accept expected terminal lists or dispositions from a
client.

Humans retain legal and governance authority. System recommendations and real human approvals are separate states. A fixture actor may exercise approval behavior only when every representation says **SYNTHETIC TEST APPROVAL**; never imply that a synthetic approval is real.

## Verified scope

- The React experience, Bedrock-backed matching/extraction, deterministic
  verification, DataHub-native registry, live MCP impact analysis, and SDK
  write/readback path are implemented.
- The tested provider path is Amazon Bedrock Converse with the configured Claude
  Sonnet 4.5 inference profile. Model access, credential source, synthetic
  document-transmission permission, and request cost remain operator
  responsibilities.
- `fixtures/extraction-qualification/` and
  `fixtures/matching-qualification/` are challenge corpora. Their credentialed
  provider runners must not be described as passing unless every selected
  required case passes.

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

For the API without silently resetting an existing graph:

```bash
./scripts/start_covenant.sh
./scripts/run_verified_demo.sh
```

`run_verified_loop.sh` is an intentional reset/reseed verification path.
`start_covenant.sh` preserves an existing graph and seeds only when the canonical
source is absent. Do not blur these behaviors.

The judge-facing browser flow starts at `http://127.0.0.1:5173/analyze`.
`run_verified_demo.sh` exercises the existing canonical change and does not
invoke the Bedrock document-upload flow.

## Scope and safety

- Unless a current explicit commission authorizes it, do not expand the existing
  frontend or model integration, or add a hosted service, Slack or Jira
  integration, broad contract parser, production integration, or
  machine-unlearning feature or claim.
- Even when a frontend is authorized, bind it to the real API; do not
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
raw generated evidence and API run state remain under ignored `smoke-test/`.
The only public evidence exception is deliberately curated, visually inspected,
and sanitized content under `examples/`. Tracked runtime code must not depend on
any ignored directory. Any contradiction between implementation convenience and
the current commission resolves in favor of truth, privacy, human authority, and
the acceptance criteria.
