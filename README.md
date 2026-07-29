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

Gate 2 adds a bounded, literal change-to-action slice for the fictional Atlas
Signals v3 and v4 documents. Extraction produces cited candidate rules but does
not activate them. Inspect the candidate-only result with:

```bash
PYTHONPATH=. .venv/bin/python scripts/run_change_to_action.py
```

Run the explicit test activation and live DataHub loop with:

```bash
PYTHONPATH=. .venv/bin/python scripts/run_change_to_action.py --synthetic-approve
```

The second command records only a **SYNTHETIC TEST APPROVAL**. It does not claim
real legal or governance approval. Covenant turns a reviewed source-data
obligation change into a graph-derived operational response plan; it does not
determine legal compliance or perform enforcement.

Gate 3 exposes the same reviewed change-to-action loop through a local FastAPI
boundary. Start the pinned DataHub runtime and API without resetting an existing
graph:

```bash
cp .env.example .env
./scripts/start_covenant.sh
```

The API documentation is available at `http://127.0.0.1:8000/docs`. In another
terminal, run the canonical activation, impact, writeback, and replay proof:

```bash
./scripts/run_verified_demo.sh
```

The API persists local orchestration state only under ignored `smoke-test/`.
DataHub remains authoritative for graph membership and native decision receipts.

The approved Gate 5 React integration lives in `frontend/` and uses the real API
by default:

```bash
cd frontend
cp .env.example .env
npm ci
npm run dev
```

Open `http://localhost:5173/changes`. When the API uses another port, set
`VITE_COVENANT_API_URL` in `frontend/.env`. Development CORS is narrowly limited
to the two loopback Vite origins through `COVENANT_CORS_ORIGINS`; production is
intended to be same-origin. Fixture mode is explicit and never a runtime
fallback.

Ordinary `start_covenant.sh` invokes `scripts/ensure_fixture.py`: it reads the
canonical governed source and seeds the representative native graph only when
that source is absent. It preserves existing graph and decision state. The
separate `run_verified_loop.sh` remains the intentional reset/reseed path.

This is deliberately a local replay path, not a hosted-access claim. Internal
commissions, reports, and generated evidence remain local and ignored. No
public service or external action integration is included.
