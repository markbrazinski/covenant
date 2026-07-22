#!/usr/bin/env python3
from __future__ import annotations

import json

from src.workflow.impact import analyse, write_results


if __name__ == "__main__":
    report = analyse()
    write_results(report)
    print(json.dumps(report["counts"], indent=2, sort_keys=True))
