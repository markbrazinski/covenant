# Covenant Repository Instructions

## Gate 0 contract

Covenant tests this thesis: when a source-data obligation changes, DataHub determines which downstream uses remain allowed, must stop, require remediation, or require a human decision, and Covenant records the response without touching unaffected assets.

The canonical result is exactly **1 allowed / 2 remediate / 1 stop proposed / 1 human review / 1 unaffected**. Gate 0 is a bounded feasibility test, not a product build. DataHub lineage and metadata must derive the affected set; no hidden graph or terminal outcome keyed by an asset name, URN, branch, or list position is acceptable. Prefer deterministic policy logic.

Humans retain legal and governance authority. System recommendations and real human approvals are separate states. A fixture actor may exercise approval behavior only when every representation says **SYNTHETIC TEST APPROVAL**; never imply that a synthetic approval is real.

## Scope and safety

- Do not build a frontend, Slack or Jira integration, broad contract parser, production integration, or machine-unlearning feature or claim.
- Never put secrets, raw environment identifiers, private endpoints, account data, raw exports, or credentials in tracked files.
- Sanitize generated evidence before staging; visually inspect any evidence screenshot before copying it into `smoke-test/screenshots/`.
- Record commands, exact versions, results, limitations, and deviations while work proceeds.
- Do not create a remote or push without explicit owner approval.
- Do not begin Gate 1 without a new commission following an explicit owner verdict.

Before implementation, read `docs/commissions/gate-0-smoke-test.md`. Maintain `docs/gates/gate-0-report.md` throughout execution. Any contradiction between implementation convenience and the commission resolves in favor of truth, privacy, and the acceptance criteria.
