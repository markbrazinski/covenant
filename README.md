# Covenant

Covenant is a bounded, deterministic proof that DataHub lineage and metadata can route a changed source-data obligation to affected native assets. The synthetic graph contains a DataHub Dashboard, two MLModels, a delivery DataFlow/DataJob, canonical datasets, and an unrelated control.

The expected result is exactly one allowed dashboard, two models requiring remediation, one proposed delivery stop, one human review, and one unaffected control. Humans retain approval authority; Covenant records recommendations and receipts but does not claim legal judgment, pipeline stoppage, or machine unlearning.

The supported runtime is the official local DataHub Quickstart, pinned to Core
v1.6.0. Bootstrap it on a clean machine with Docker and Python 3.11 available:

```bash
cp .env.example .env
./scripts/bootstrap_runtime.sh
./scripts/run_verified_loop.sh
```

The first command creates `.venv`, installs the pinned project and test
dependencies, and starts DataHub. The second performs deterministic reset,
live MCP-derived analysis, native writeback/readback, regressions, and final
verification. Re-running it is the supported reset/replay path.

This is deliberately a local replay path, not a hosted-access claim. Internal
commissions, reports, and generated evidence remain local and ignored. No
public service, UI, or external action integration is included.
