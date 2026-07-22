# Covenant Repository Instructions

## Gate 1A contract

Covenant tests this thesis: when a source-data obligation changes, DataHub determines which downstream uses remain allowed, must stop, require remediation, or require a human decision, and Covenant records the response without touching unaffected assets.

The canonical result is exactly **1 allowed / 2 remediate / 1 stop proposed / 1 human review / 1 unaffected**. Gate 1A uses native DataHub Dashboard, MLModel, DataFlow, and DataJob entities. DataHub MCP lineage must derive the affected set and defensible paths; no hidden graph or terminal outcome keyed by an asset name, URN, branch, or list position is acceptable. Prefer deterministic policy logic.

Humans retain legal and governance authority. System recommendations and real human approvals are separate states. A fixture actor may exercise approval behavior only when every representation says **SYNTHETIC TEST APPROVAL**; never imply that a synthetic approval is real.

## Scope and safety

- Do not build a frontend, hosted service, Slack or Jira integration, broad contract parser, production integration, or machine-unlearning feature or claim.
- Never put secrets, raw environment identifiers, private endpoints, account data, raw exports, or credentials in tracked files.
- Sanitize generated evidence before staging; visually inspect any evidence screenshot before copying it into `smoke-test/screenshots/`.
- Record commands, exact versions, results, limitations, and deviations while work proceeds.
- Do not create a remote or push without explicit owner approval.
- Do not publish, create a remote, or begin Gate 1B without explicit owner approval.

Gate commissions and reports remain local under ignored `docs/`; generated evidence remains under ignored `smoke-test/`. Any contradiction between implementation convenience and the current commission resolves in favor of truth, privacy, and the acceptance criteria.
