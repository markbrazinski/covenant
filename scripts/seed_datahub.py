#!/usr/bin/env python3
from __future__ import annotations

import json

from src.datahub_client.core import seed_fixture


if __name__ == "__main__":
    print(json.dumps(seed_fixture(), indent=2, sort_keys=True))
