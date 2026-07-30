from __future__ import annotations

import json
import socket
from pathlib import Path

import httpx

from scripts.preflight_port import port_is_available
from scripts.run_http_demo import canonical_fixture_change

ROOT = Path(__file__).resolve().parents[1]


def test_api_port_preflight_detects_an_occupied_port():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    host, port = listener.getsockname()
    try:
        available, error = port_is_available(host, port)
        assert available is False
        assert error
    finally:
        listener.close()

    available, error = port_is_available(host, port)
    assert available is True
    assert error is None


def test_http_demo_requests_canonical_fixture_instead_of_selecting_a_list():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "change_id": "CHANGE-canonical",
                "candidate_hash": "a" * 64,
            },
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://covenant.test",
    ) as client:
        change = canonical_fixture_change(client)

    assert change["change_id"] == "CHANGE-canonical"
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/api/changes/analyze"
    assert json.loads(requests[0].content) == {"fixture_id": "atlas_v3_v4"}


def test_frontend_dev_server_binds_to_documented_ipv4_host():
    package = json.loads((ROOT / "frontend" / "package.json").read_text())
    assert package["scripts"]["dev"] == "vite --host 127.0.0.1"


def test_startup_preflights_api_port_before_runtime_bootstrap():
    script = (ROOT / "scripts" / "start_covenant.sh").read_text()
    assert script.index('scripts/preflight_port.py "$api_host" "$api_port"') < (
        script.index("./scripts/bootstrap_runtime.sh")
    )
