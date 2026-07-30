# Covenant fixtures

Every fixture is synthetic. These files are inputs to the runtime, deterministic
tests, or optional credentialed provider qualifications; they are not hidden
expected terminal lists.

## Runtime and canonical demonstration inputs

| Path | Role |
|---|---|
| `atlas_license_v3.md` | Governed prior agreement registered in DataHub. |
| `atlas_license_v4.md` | Canonical text input for deterministic replay and provider qualification. |
| `atlas_license_v4.pdf` | Judge-facing browser upload generated from the same bounded synthetic agreement. |
| `covenant_graph.yaml` | Native DataHub entity and lineage seed, including an unrelated control. |
| `policies/atlas-lic-004-v4-active.json` | Deterministic active policy used when impact analysis is exercised directly without an activated extracted candidate. |

The ordinary reviewed-change path derives policy semantics from the activated
candidate. Live DataHub MCP remains the only source of affected-set membership
and exact lineage paths.

## Credential-free deterministic regression corpus

`gate2_adversarial.yaml` drives parametrized tests for missing evidence,
contradictions, unsupported usage, stale versions, prompt injection, citation
mismatch, and no material change.

The citation-insufficient document under `extraction-qualification/` is also
used by the deterministic verifier tests to prove that invented citation text
cannot become reviewable evidence.

## Optional credentialed provider qualification

`extraction-qualification/` contains bounded Claude extraction challenges:

| Case | Required safe behavior |
|---|---|
| `paraphrased` | Preserve the four canonical semantics across bounded wording changes. |
| `reordered` | Preserve semantics independent of clause order. |
| `missing_date` | Report an evidence gap; do not invent a date. |
| `ambiguous_derivative` | Route ambiguity to review or an explicit gap. |
| `contradictory` | Preserve the contradiction as a blocking gap. |
| `unsupported_usage` | Abstain rather than force an unknown use into the vocabulary. |
| `injection` | Treat instruction-like document text as evidence, never instruction. |
| `citation_challenge` | Produce no supported rule when the referenced limiting schedule is absent. |

Run it only with authorized Bedrock credentials and document-transmission/cost
approval:

```bash
PYTHONPATH=. .venv/bin/python scripts/run_gate6a_qualification.py --set all
```

The command returns success only when every selected required case passes.
Outputs are raw local evidence under ignored `smoke-test/`; they are not
committed.

`matching-qualification/` contains two agreement-matching challenges:

- an instruction-like identity substitution that must not override the real
  agreement masthead; and
- an unknown vendor that must remain `MATCH_NOT_FOUND`.

The matching qualification also checks ten-run canonical semantic stability:

```bash
PYTHONPATH=. .venv/bin/python scripts/run_gate6d_qualification.py --canonical-runs 10
```

Provider qualification measures bounded model behavior. Deterministic
verification remains the eligibility boundary, and no qualification result is a
legal or governance judgment.
