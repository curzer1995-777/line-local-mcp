from __future__ import annotations

import argparse
import json
import sys

from .bootstrap import BootstrapError, setup_key
from .database import LineDatabaseError
from .repository import LineRepository
from .server import create_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only MCP server for local LINE Desktop history"
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="Use stdio for local AI clients or streamable-http for a loopback tunnel.",
    )
    parser.add_argument(
        "--setup-key",
        action="store_true",
        help="Run the one-time, local macOS database-key setup.",
    )
    parser.add_argument(
        "--port", type=int, default=8765, help="Loopback HTTP port (default: 8765)."
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Check database access and exit without starting an MCP server.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.setup_key:
        try:
            setup_key()
        except (BootstrapError, LineDatabaseError) as exc:
            print(f"LINE MCP key setup failed: {exc}", file=sys.stderr)
            raise SystemExit(1) from None
        return
    if args.doctor:
        try:
            print(json.dumps(LineRepository().status(), ensure_ascii=False, indent=2))
        except LineDatabaseError as exc:
            print(f"LINE MCP is not ready: {exc}", file=sys.stderr)
            raise SystemExit(1) from None
        return
    server = create_server()
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(
            transport="streamable-http",
            host="127.0.0.1",
            port=args.port,
            streamable_http_path="/mcp",
            json_response=True,
            stateless_http=True,
        )


if __name__ == "__main__":
    main()
