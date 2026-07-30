#!/usr/bin/env python3
from __future__ import annotations

import json

from covenant.registry import DataHubAgreementRegistry, atlas_agreement_record


def main() -> int:
    record = DataHubAgreementRegistry().seed_and_wait(atlas_agreement_record())
    print(
        json.dumps(
            {
                "status": "SEEDED",
                "registry_urn": record.registry_urn,
                "vendor_name": record.vendor_name,
                "obligation_id": record.obligation_id,
                "current_version": record.current_version,
                "prior_document_hash": record.prior_document_hash,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
