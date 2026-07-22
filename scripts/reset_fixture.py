#!/usr/bin/env python3
from __future__ import annotations

import json

from src.datahub_client.core import load_fixture, seed_fixture, soft_delete_entities


if __name__ == "__main__":
    fixture = load_fixture()
    entity_ids = [entity["id"] for entity in fixture["entities"]]
    soft_delete_entities(entity_ids)
    result = seed_fixture(fixture, preserve_decisions=False)
    result["reset"] = "Covenant-owned entities soft-deleted then deterministically re-seeded"
    print(json.dumps(result, indent=2, sort_keys=True))
