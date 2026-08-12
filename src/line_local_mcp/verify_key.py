from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from .database import open_encrypted_snapshot


def verify_key(snapshot: Path, candidate: str) -> bool:
    if not re.fullmatch(r"[0-9a-fA-F]{32}", candidate):
        return False
    try:
        with open_encrypted_snapshot(snapshot, candidate) as connection:
            tables = {
                row[0]
                for row in connection.cursor().execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            return {"_message", "_chat", "_contact"}.issubset(tables)
    except Exception:
        return False


def main() -> None:
    snapshot_value = os.environ.get("LINE_MCP_VERIFY_SNAPSHOT")
    candidate = sys.stdin.read(128).strip()
    if not snapshot_value or not verify_key(Path(snapshot_value), candidate):
        print("NO")
        raise SystemExit(1)
    print("OK")


if __name__ == "__main__":
    main()
