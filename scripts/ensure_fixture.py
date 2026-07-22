#!/usr/bin/env python3
from __future__ import annotations

from src.datahub_client.core import entity_urn, native_custom_properties, seed_fixture


if __name__ == "__main__":
    source_urn = entity_urn("vendor_demographics_raw")
    try:
        properties = native_custom_properties(source_urn)
    except RuntimeError:
        counts = seed_fixture(preserve_decisions=True)
        print(f"Seeded missing canonical Covenant graph: {counts}")
    else:
        if properties.get("covenant.obligation_id") != "ATLAS-LIC-004":
            raise SystemExit("Existing source identity failed Covenant obligation validation")
        print("Canonical Covenant graph already exists; no reset performed")
