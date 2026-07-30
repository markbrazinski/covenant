#!/usr/bin/env python3
from __future__ import annotations

import argparse
import socket
import sys


def port_is_available(host: str, port: int) -> tuple[bool, str | None]:
    try:
        addresses = socket.getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
            flags=socket.AI_PASSIVE,
        )
    except socket.gaierror as exc:
        return False, str(exc)

    errors: list[str] = []
    for family, socktype, protocol, _, address in addresses:
        probe = socket.socket(family, socktype, protocol)
        try:
            probe.bind(address)
        except OSError as exc:
            errors.append(str(exc))
        else:
            return True, None
        finally:
            probe.close()
    return False, "; ".join(dict.fromkeys(errors))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail fast when the configured Covenant API port is unavailable."
    )
    parser.add_argument("host")
    parser.add_argument("port", type=int, choices=range(1, 65_536))
    args = parser.parse_args()

    available, error = port_is_available(args.host, args.port)
    if available:
        return 0
    print(
        (
            f"Covenant API port preflight failed: {args.host}:{args.port} "
            f"is unavailable ({error or 'bind failed'}). "
            "Stop the conflicting process or configure a coordinated alternate "
            "COVENANT_API_PORT before retrying."
        ),
        file=sys.stderr,
    )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
