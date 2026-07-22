#!/usr/bin/env python3
from __future__ import annotations

import json

from src.datahub_client.core import load_fixture, seed_fixture


if __name__ == "__main__":
    fixture = load_fixture()
    result = seed_fixture(fixture, preserve_decisions=False)
    result["reset"] = "Covenant-owned base aspects deterministically re-seeded; decision properties cleared"
    print(json.dumps(result, indent=2, sort_keys=True))
