#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

from src.obligations.candidate import SYNTHETIC_APPROVAL_LABEL

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.getenv("COVENANT_API_URL", "http://127.0.0.1:8000")
OUTPUT = ROOT / "smoke-test" / "gate3-http-demo.json"


def require(response: httpx.Response) -> dict:
    response.raise_for_status()
    return response.json()


def canonical_fixture_change(client: httpx.Client) -> dict:
    return require(
        client.post(
            "/api/changes/analyze",
            json={"fixture_id": "atlas_v3_v4"},
        )
    )


if __name__ == "__main__":
    with httpx.Client(base_url=BASE_URL, timeout=120) as client:
        health = require(client.get("/api/health"))
        change = canonical_fixture_change(client)
        activation = require(
            client.post(
                f"/api/changes/{change['change_id']}/activate",
                json={
                    "reviewed_candidate_hash": change["candidate_hash"],
                    "label": SYNTHETIC_APPROVAL_LABEL,
                    "actor": "synthetic_gate3_reviewer",
                    "review_note": "Gate 3 HTTP software test only; no real legal or governance approval.",
                },
            )
        )
        impact = require(client.post(f"/api/changes/{change['change_id']}/impact"))
        written = require(client.post(f"/api/runs/{activation['run_id']}/writeback"))
        replay = require(client.post(f"/api/runs/{activation['run_id']}/replay"))
    first_receipts = {item["decision_id"]: item for item in written["receipts"]}
    replay_receipts = {item["decision_id"]: item for item in replay["receipts"]}
    artifact = {
        "health": health,
        "change": change,
        "activation": activation,
        "impact": impact,
        "written": written,
        "replay": replay,
        "replay_identity_stable": first_receipts.keys() == replay_receipts.keys(),
        "replay_timestamps_stable": all(
            first_receipts[key]["recorded_at"] == replay_receipts[key]["recorded_at"]
            for key in first_receipts
        ),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    OUTPUT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    os.chmod(OUTPUT, 0o600)
    print(
        json.dumps(
            {
                "run_id": replay["run_id"],
                "stage": replay["stage"],
                "counts": replay["counts"],
                "receipts": len(replay["receipts"]),
                "replay_identity_stable": artifact["replay_identity_stable"],
                "replay_timestamps_stable": artifact["replay_timestamps_stable"],
            },
            indent=2,
            sort_keys=True,
        )
    )
