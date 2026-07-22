# Covenant

Covenant is a bounded, deterministic proof that DataHub lineage and metadata can route a changed source-data obligation to affected native assets. The synthetic graph contains a DataHub Dashboard, two MLModels, a delivery DataFlow/DataJob, canonical datasets, and an unrelated control.

The expected result is exactly one allowed dashboard, two models requiring remediation, one proposed delivery stop, one human review, and one unaffected control. Humans retain approval authority; Covenant records recommendations and receipts but does not claim legal judgment, pipeline stoppage, or machine unlearning.

Run the local proof against the pinned DataHub environment:

```bash
.venv/bin/python -m scripts.reset_fixture
.venv/bin/python -m scripts.run_impact_analysis
.venv/bin/python -m scripts.apply_writeback --synthetic-override
.venv/bin/pytest -q
.venv/bin/python -m scripts.verify_smoke_test
```

Internal commissions, reports, and generated evidence remain local and ignored. No remote, hosted service, UI, external integration, or Gate 1B scope is included.
